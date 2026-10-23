from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from app.tools.registry import get_tool, list_tools

router = APIRouter(prefix="/v1")


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, Any]


@router.get("/capabilities")
def capabilities():
    return {"capabilities": list_tools()}


@router.post("/tools/execute")
def execute_tool(request: ToolRequest):
    tool = get_tool(request.name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown tool")
    try:
        result = tool(request.arguments)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": request.name, "result": result}
