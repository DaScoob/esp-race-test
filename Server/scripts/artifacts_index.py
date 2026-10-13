import hashlib
import html
import pathlib
import sys

ARTIFACTS_DIR = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts").resolve()

TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>esp-race-test artefakte</title>
<link rel="icon" href="data:,">
<style>
body{{margin:0;background:#050b09;color:#f4f8f5;font:1rem/1.5 Inter,ui-sans-serif,system-ui,sans-serif;padding:clamp(1rem,4vw,3rem)}}
h1{{font-weight:800;letter-spacing:-.02em;margin:0 0 .3rem}}
p{{color:#a5b4ae;margin:0 0 1.5rem;font-size:.85rem}}
table{{border-collapse:collapse;width:100%;max-width:56rem;border:1px solid rgba(234,248,240,.16);border-radius:.75rem;overflow:hidden;font-size:.9rem}}
th,td{{text-align:left;padding:.55rem .8rem;border-bottom:1px solid rgba(234,248,240,.1);font-variant-numeric:tabular-nums}}
th{{font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:#a5b4ae}}
tr:last-child td{{border-bottom:0}}
a{{color:#9bea75;font-weight:650}}
code{{color:#a5b4ae;font-size:.78rem;overflow-wrap:anywhere}}
</style>
</head>
<body>
<h1>esp-race-test artefakte</h1>
<p>Dieses Verzeichnis enthält ausschließlich versionierte Projekt-Snapshots (ZIP). Keine Konfiguration, keine Schlüssel, keine Laufzeitdaten.</p>
<table><thead><tr><th>Datei</th><th>Größe</th><th>Erstellt</th><th>SHA-256</th></tr></thead><tbody>
{rows}
</tbody></table>
</body>
</html>
"""


def main() -> None:
    entries = sorted(
        (path for path in ARTIFACTS_DIR.iterdir() if path.is_file() and path.name != "index.html"),
        key=lambda path: path.name,
        reverse=True,
    )
    rows = []
    for path in entries:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        created = "-"
        if path.name.endswith(".zip"):
            try:
                from zipfile import ZipFile

                with ZipFile(path) as zf:
                    dates = [date_time for info in zf.infolist() for date_time in [info.date_time]]
                    if dates:
                        newest = max(dates)
                        created = f"{newest[0]:04d}-{newest[1]:02d}-{newest[2]:02d} {newest[3]:02d}:{newest[4]:02d}"
            except (ValueError, OSError):
                created = "-"
        rows.append(
            "<tr><td><a href=\"{name}\">{name}</a></td><td>{size} B</td><td>{created}</td><td><code>{digest}</code></td></tr>".format(
                name=html.escape(path.name),
                size=path.stat().st_size,
                created=created,
                digest=digest[:16] + "…",
            )
        )
    if not rows:
        rows.append("<tr><td colspan=\"4\">Keine Artefakte vorhanden</td></tr>")
    output = ARTIFACTS_DIR / "index.html"
    output.write_text(TEMPLATE.format(lines=len(entries), rows="\n".join(rows)), encoding="utf-8")
    print(f"index written: {output} ({len(entries)} entries)")


if __name__ == "__main__":
    main()