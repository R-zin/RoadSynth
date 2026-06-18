from fastapi import APIRouter,HTTPException,File

router = APIRouter()
@router.get("/files/{filename}")
async def read_files(filename: File = File(...)):
    try:
        return {"filename": filename}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
