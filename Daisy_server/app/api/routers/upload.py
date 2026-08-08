from fastapi import APIRouter, UploadFile, File, HTTPException
import aiofiles
import os
import uuid
from app.core.config import settings, get_writable_data_dir

router = APIRouter()

# 冻结环境下包内只读,上传目录必须落在可写数据目录(见 config.get_writable_data_dir)
UPLOAD_DIR = os.path.join(get_writable_data_dir(), "static", "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
BACKGROUND_DIR = os.path.join(UPLOAD_DIR, "backgrounds")

# Ensure directories exist
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(BACKGROUND_DIR, exist_ok=True)

async def save_upload_file(file: UploadFile, directory: str) -> str:
    # Generate a unique filename
    extension = os.path.splitext(file.filename)[1]
    if not extension:
        extension = ".png" # Default to png if no extension
    
    filename = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join(directory, filename)
    
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    return filename

@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
        
    filename = await save_upload_file(file, AVATAR_DIR)
    
    # Construct the URL (Assuming the server is running on the same host)
    # Ideally, we should return a relative path or a full URL based on configuration
    # For now, returning relative path from static mount point
    return {"url": f"/static/uploads/avatars/{filename}"}

@router.post("/background")
async def upload_background(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
        
    filename = await save_upload_file(file, BACKGROUND_DIR)
    
    return {"url": f"/static/uploads/backgrounds/{filename}"}
