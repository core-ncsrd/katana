from fastapi import FastAPI, Request
import uvicorn
import subprocess

app = FastAPI()

@app.post("/deploy")
async def deploy_handler(request: Request):
    # Read the input just to accept it (not using it)
    _ = await request.json()

    try:
        # Run your command using existing open5gsK8s.json
        cmd = ["sudo", "katana", "k8s", "deploy", "-f", "open5gsK8s.json"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8005)
