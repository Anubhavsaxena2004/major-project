# BandwidthBridge

This project implements the adaptive low-bandwidth lecture playback architecture described in the proposal.

## Structure

- `backend/` – FastAPI server that serves lecture manifests and media assets
- `extension/` – Chrome extension files for the adaptive cache and player shell
- `demo/` – a sample lecture page to test the extension against
- `packages/` – generated lecture package data used by the extension

## Run the API

```bash
cd c:/Users/anubh/Videos/major-project
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open `http://localhost:8000/` and the lecture demo page.

## Browser extension

Load the `extension/` directory as an unpacked extension in Chrome. Open the demo page in the browser and click the extension action.

## Demo lecture package

The package under `packages/dbms-01` contains a sample `manifest.json`, pregenerated audio chunks, and slide images that simulate the lecture pipeline.
