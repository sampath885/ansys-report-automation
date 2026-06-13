"""Try opening DOCX with Microsoft Word COM."""
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
try:
    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(str(path))
    doc.Close(False)
    word.Quit()
    print("Word COM: OPEN OK")
except ImportError:
    print("pywin32 not installed")
except Exception as exc:
    print("Word COM: FAIL", exc)
