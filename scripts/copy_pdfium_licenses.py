from importlib.metadata import distribution
from pathlib import Path
import shutil

dist = distribution("pypdfium2")
files = list(dist.files or [])
license_files = [
    item for item in files
    if ".dist-info/licenses/" in str(item).replace("\\", "/")
]
if not any("BUILD_LICENSES" in str(item) for item in license_files):
    raise SystemExit(
        "pypdfium2 wheel did not expose PDFium BUILD_LICENSES; "
        "refusing to build an image without bundled notices"
    )

target = Path("/app/THIRD_PARTY_LICENSES/pypdfium2")
for item in license_files:
    source = Path(dist.locate_file(item))
    if source.is_file():
        relative = Path(str(item).split(".dist-info/licenses/", 1)[1])
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
