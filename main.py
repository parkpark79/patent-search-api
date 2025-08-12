from fastapi import FastAPI, Query
from model import analyst
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Patent Search API", description="유사 특허 검색 API", version="1.0")

@app.get("/")
def root():
    return {"message": "Patent Search API is running"}

@app.get("/search")
def search_patent(query: str = Query(..., description="검색할 기술 내용")):
    result = analyst.analyze(query)
    return result
