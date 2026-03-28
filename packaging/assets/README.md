# Branding Assets

Expected files used by EMtranscriber:

- `emtranscriber.ico`: application icon (window + EXE packaging)
- `main_sidebar_image.jpg` (or `.png`/`.jpeg`): image shown on the left side of the main window

Generate assets from source images with:

```powershell
python scripts/prepare_branding_assets.py --icon-source "C:\path\to\icon-image.png" --sidebar-source "C:\path\to\sidebar-image.jpg"
```

The script writes outputs into `packaging/assets/`.
