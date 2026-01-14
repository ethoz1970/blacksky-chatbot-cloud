"""
Download TinyLlama model from HuggingFace
"""
from huggingface_hub import hf_hub_download
from config import MODEL_REPO, MODEL_FILENAME, MODEL_DIR
import sys


def download_model():
    """Download the quantized TinyLlama model."""
    print(f"Downloading {MODEL_FILENAME} from {MODEL_REPO}...")
    print("This may take a few minutes on first run.\n")
    
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        model_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            local_dir=MODEL_DIR,
            local_dir_use_symlinks=False
        )
        print(f"\n✓ Model downloaded to: {model_path}")
        return model_path
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    download_model()
