"""Build dist/NTE Telemetry-<version>.msi: builds the exe (build.py), then packs it with WiX (installer/Package.wxs).
Needs the WiX Toolset (v4 or later, `wix` on PATH) with the UI extension:  wix extension add -g WixToolset.UI.wixext
Run with the project venv:  .venv\\Scripts\\python build_msi.py [version]   (version: 1.2.3, default the app's
own, src/version.py; a newer version installed over an older one replaces it). On GitHub, .github/workflows/release.yml
runs it whenever src/version.py gets a version not released yet."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
WORK = os.path.join(HERE, "build", "msi")


def app_version():
    """VERSION from src/version.py."""
    scope = {}
    with open(os.path.join(HERE, "src", "version.py"), encoding="utf-8") as f:
        exec(f.read(), scope)
    return scope["VERSION"]


def license_rtf(path, out):
    """The installer's licence page wants RTF; LICENSE is plain text."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    body = "\\par\n".join(text.splitlines())
    with open(out, "w", encoding="ascii", errors="replace") as f:
        f.write("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Consolas;}}\\f0\\fs16\n" + body + "\n}")


def dark_panel(img, x, w, h, logo_size, logo_y):
    """The app's background cropped into img at x..x+w, with the logo centred on it."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage, QPainter

    assets = os.path.join(HERE, "src", "assets")
    bg = QImage(os.path.join(assets, "background.png"))
    logo = QImage(os.path.join(assets, "logo.png"))
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    # a slice of the background where its road lines cross, scaled to the panel's height
    scaled = bg.scaledToHeight(h * 2, Qt.SmoothTransformation)
    p.drawImage(QRect(x, 0, w, h), scaled, QRect(scaled.width() // 2 - w, scaled.height() // 2 - h // 2, w * 2, h))
    # the logo is a square with lots of margin; draw it larger than the slot so the mark fills it
    s = round(logo_size * 1.6)
    p.drawImage(QRect(x + (w - s) // 2, logo_y - s // 2, s, s), logo.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    p.end()


def ui_bitmaps(work):
    """Installer artwork from the app's own: the banner on top of the inner pages (493x58) and the picture behind
    the first and last pages (493x312). WixUI draws its text in black on them, so it stays on white and the
    dark panel goes where there is none: the banner's right end, the picture's left strip."""
    from PySide6.QtGui import QColor, QGuiApplication, QImage

    QGuiApplication.instance() or QGuiApplication([])
    out = {}
    for name, w, h, panel in (("Banner", 493, 58, (493 - 96, 96, 58, 29)),
                              ("Dialog", 493, 312, (0, 164, 110, 120))):
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(QColor("white"))
        x, pw, logo, logo_y = panel
        dark_panel(img, x, pw, h, logo, logo_y)
        path = os.path.join(work, f"{name}.bmp")
        img.save(path, "BMP")
        out[name] = path
    return out


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else app_version()
    if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,5}", version):
        sys.exit(f"version must look like 1.2.3, not {version!r}")

    subprocess.run([sys.executable, os.path.join(HERE, "build.py")], check=True)

    os.makedirs(WORK, exist_ok=True)
    rtf = os.path.join(WORK, "License.rtf")
    license_rtf(os.path.join(HERE, "LICENSE"), rtf)
    art = ui_bitmaps(WORK)
    msi = os.path.join(DIST, f"NTE Telemetry-{version}.msi")
    subprocess.run([
        "wix", "build", os.path.join(HERE, "installer", "Package.wxs"),
        "-arch", "x64",
        "-ext", "WixToolset.UI.wixext",
        "-d", f"Version={version}",
        "-d", f"ExePath={os.path.join(DIST, 'NTE Telemetry.exe')}",
        "-d", f"IconPath={os.path.join(HERE, 'src', 'assets', 'app.ico')}",
        "-d", f"LicenseRtf={rtf}",
        "-d", f"BannerBmp={art['Banner']}",
        "-d", f"DialogBmp={art['Dialog']}",
        "-intermediatefolder", WORK,
        "-o", msi,
    ], check=True)
    print("built", msi)


if __name__ == "__main__":
    main()
