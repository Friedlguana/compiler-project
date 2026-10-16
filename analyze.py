"""Auto-detect a source language, syntax-check it, and generate supported TAC."""
import argparse
from pathlib import Path
import sys
from fastapi import HTTPException
from pydantic import ValidationError
from web.app import AnalyzeRequest, analyze, build_compiler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file",type=Path)
    parser.add_argument("--language",default="auto",
                        choices=("auto","python","java","c","cpp","javascript","shared"))
    args=parser.parse_args()
    try:
        source=args.file.read_text(encoding="utf-8-sig")
        payload=AnalyzeRequest(source=source,language=args.language)
        build_compiler()
        result=analyze(payload)
    except (OSError,RuntimeError,ValidationError,HTTPException) as error:
        print("ERROR:",getattr(error,"detail",str(error)),file=sys.stderr)
        return 2
    detected=result["language"]
    print("DETECTED LANGUAGE:",detected["name"])
    print(detected["reason"])
    if detected["ambiguous"]:
        print("Possible languages:",", ".join(detected["candidates"]))
    print(result["output"])
    if result["syntax"]!="success":
        return 1
    return 0 if result["translation"]=="success" else 3


if __name__=="__main__":
    raise SystemExit(main())

