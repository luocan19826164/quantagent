
import sys
import os

# Add the project root to sys.path
sys.path.append('/Users/mac/Documents/project/cursor/quantagent/backend')

from tool.capability_manifest import get_capability_manifest_text

try:
    manifest = get_capability_manifest_text()
    print("--- GENERATED MANIFEST ---")
    print(manifest)
    print("--- END OF MANIFEST ---")
except Exception as e:
    print(f"Error generating manifest: {e}")
    import traceback
    traceback.print_exc()
