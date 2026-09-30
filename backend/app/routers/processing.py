"""Manual upload flow: MinIO video + annotated frame logs + PostgreSQL events."""
from __future__ import annotations
import json, os, shutil
from pathlib import Path
from typing import Any
from uuid import uuid4
import cv2, requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.routers.events import manager
from app.storage.storage_service import StorageService

router=APIRouter(prefix="/source", tags=["Video processing"])
storage=StorageService(); UPLOAD_DIR=Path(os.getenv("UPLOAD_DIRECTORY","/media/uploads"))
SERVICE_URLS={"classroom":os.getenv("EXAM_INFERENCE_URL","http://exam_inference:8002/infer"),"mall":os.getenv("MALL_INFERENCE_URL","http://mall_inference:8001/infer"),"traffic":os.getenv("TRAFFIC_INFERENCE_URL","http://traffic_inference:8003/infer"),"railway":os.getenv("SUBWAY_INFERENCE_URL","http://subway_inference:8004/infer")}

def label_and_severity(event: dict[str,Any]) -> tuple[str,str,float]:
    detections=event.get("detections") or []; rule=event.get("rule_result") or {}
    confidence=max([float(d.get("confidence",0)) for d in detections] or [0.0])
    matched=rule.get("matched_rules") or []
    label=(str(matched[0]).replace("_rule","").replace("_"," ") if matched else str((detections[0] if detections else {}).get("class_name","normal activity")).replace("_"," "))
    severity=str(rule.get("severity") or ("high" if matched else "low"))
    return label.title(),severity,min(max(confidence,0.0),1.0)

def make_preview(source: Path,event: dict[str,Any],prefix: str,label: str) -> str|None:
    cap=cv2.VideoCapture(str(source)); cap.set(cv2.CAP_PROP_POS_FRAMES,int(event.get("frame_index",0))); ok,frame=cap.read(); cap.release()
    if not ok: return None
    for det in event.get("detections") or []:
        x1,y1,x2,y2=[int(v) for v in det.get("bbox",[0,0,0,0])]; name=str(det.get("class_name",label)); score=float(det.get("confidence",0))*100
        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,0,255),2); cv2.putText(frame,f"{name} {score:.0f}%",(x1,max(24,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,0,255),2)
    cv2.putText(frame,label,(20,35),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,255),2)
    temp=f"/tmp/{uuid4().hex}.jpg"; cv2.imwrite(temp,frame)
    object_name=f"frames/{prefix}/{event.get('event_id',uuid4().hex)}.jpg"
    try: return storage.upload_video(temp,object_name,"image/jpeg")
    finally:
        if os.path.exists(temp): os.remove(temp)

def values(event: dict[str,Any],video_object:str,filename:str,preview:str|None)->dict[str,Any]:
    label,severity,confidence=label_and_severity(event)
    payload={**event,"video_object":video_object,"snapshot_object":preview,"uploaded_filename":filename,"review_status":"pending","detected_class":label}
    return {"event_id":str(event.get("event_id") or uuid4()),"camera_id":str(event.get("camera_id","uploaded-video")),"environment":str(event.get("domain","unknown")),"event_type":label,"severity":severity,"confidence":confidence,"payload":json.dumps(payload,default=str)}

def persist(items:list[dict[str,Any]])->int:
    db=SessionLocal(); count=0
    try:
        for item in items:
            result=db.execute(text("""INSERT INTO raw_events(event_id,camera_id,environment,event_type,severity,confidence,payload) VALUES(:event_id,:camera_id,:environment,:event_type,:severity,:confidence,CAST(:payload AS JSONB)) ON CONFLICT(event_id) DO NOTHING RETURNING id"""),item)
            if result.first(): count+=1
        db.commit(); return count
    finally: db.close()

@router.post("/{environment}/upload")
async def upload_and_process(environment:str,file:UploadFile=File(...),camera_id:str=Form("uploaded-video")):
    if environment not in SERVICE_URLS: raise HTTPException(400,f"Unsupported environment: {environment}")
    if not file.filename: raise HTTPException(400,"A video file is required")
    UPLOAD_DIR.mkdir(parents=True,exist_ok=True); suffix=Path(file.filename).suffix.lower() or ".mp4"; upload_id=uuid4().hex; local=UPLOAD_DIR/f"{upload_id}{suffix}"; video_object=f"videos/{environment}/{upload_id}_{Path(file.filename).name}"
    try:
        with local.open("wb") as out: shutil.copyfileobj(file.file,out)
        if not storage.upload_video(str(local),video_object,file.content_type or "video/mp4"): raise HTTPException(502,"Could not store video in MinIO")
        response=requests.post(SERVICE_URLS[environment],json={"source":f"/media/uploads/{local.name}","camera_id":camera_id,"max_frames":180},timeout=300); response.raise_for_status(); events=response.json().get("events",[])
        records=[]
        for event in events:
            event["camera_id"]=camera_id; event["domain"]=environment; label,_,_=label_and_severity(event); preview=make_preview(local,event,upload_id,label); record=values(event,video_object,file.filename,preview); records.append(record)
        stored=persist(records)
        for event,record in zip(events,records):
            payload=json.loads(record["payload"]); preview=payload.get("snapshot_object")
            await manager.broadcast({"id":record["event_id"],"camera_name":record["camera_id"],"environment":record["environment"],"activity_type":record["event_type"],"severity":record["severity"],"confidence":record["confidence"],"detected_at":event.get("created_at"),"status":"pending","json_log":payload,"snapshot_url":"/api/videos/preview/" + preview if preview else None})
        return {"status":"processed","environment":environment,"object_path":video_object,"presigned_url":storage.get_video_url(video_object),"event_count":len(events),"stored_event_count":stored,"json_logs":events}
    except requests.RequestException as exc: raise HTTPException(502,f"Inference service failed: {exc}") from exc