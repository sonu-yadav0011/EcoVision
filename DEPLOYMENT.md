# ECOVISSION — focused UI and deployment

## Core pages
1. Main Dashboard
2. Single Image Analysis
3. Two Image Comparison

## Add these project files to your GitHub repository
- `app.py` and `requirements.txt` from this package
- Your existing `process_satellite.py`
- Your existing `models/` directory with config, metadata, and weights

Do not upload `.venv/`, `__pycache__/`, or local `data/ecovission.db`.

## Test locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy with Streamlit Community Cloud
1. Push the project files above to GitHub.
2. Visit https://share.streamlit.io and sign in with GitHub.
3. Click Create app.
4. Select the repository, branch (usually `main`), and `app.py`.
5. In Advanced settings, select Python 3.11 or 3.12 and deploy.
6. Check build logs if dependency installation fails.

Official instructions:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

## Important
- TensorFlow is a large dependency. Model startup may be slow or exceed Community Cloud resource limits; test the deployment before sharing widely.
- Community Cloud does not guarantee persistence of local file storage. SQLite history may be deleted. Use a managed external database for reliable online history.
- Uploaded images are processed in memory and are not permanently stored by this package.
- Keep the model files in the repository or a supported external model store. Check GitHub file-size limits before pushing.
- RGB heuristics and pixel differences are exploratory, not validated deforestation detection.

## Git commands
```bash
git add app.py requirements.txt process_satellite.py models/
git commit -m "Refine ECOVISSION core dashboard and UI"
git push origin main
```
