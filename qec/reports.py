"""Self-contained, escaped HTML reports with pointwise uncertainty plots."""

from html import escape


def chart(points):
    points = [p for p in points if p.get("shots", 0)]
    if not points:
        return '<p>No samples collected.</p>'
    xmin, xmax = min(p['p'] for p in points), max(p['p'] for p in points)
    ymax = max(max(p['interval'][1] for p in points), 0.001)
    def x(p):
        return 350 if xmax == xmin else 65 + 575 * (p - xmin) / (xmax - xmin)
    def y(rate):
        return 280 - 235 * rate / ymax
    parts = ['<svg viewBox="0 0 700 340" role="img" aria-label="Logical error probability with 95 percent Wilson intervals">']
    for i in range(5):
        v = ymax * i / 4
        parts.append(f'<path d="M65 {y(v):.2f} H640" stroke="#dde5e1"/><text x="58" y="{y(v)+4:.2f}" text-anchor="end">{v:.3g}</text>')
    for p in sorted(set(p['p'] for p in points)):
        parts.append(f'<text x="{x(p):.2f}" y="303" text-anchor="middle">{p:g}</text>')
    palette = ['#08786d', '#8062a5', '#a56925', '#386eaa']
    for i, d in enumerate(sorted(set(p['distance'] for p in points))):
        group = sorted([p for p in points if p['distance'] == d], key=lambda p:p['p'])
        color = palette[i % len(palette)]
        path = ' '.join(f'{x(p["p"]):.2f},{y(p["rate"]):.2f}' for p in group)
        parts.append(f'<polyline points="{path}" stroke="{color}" fill="none" stroke-width="2"/>')
        parts.append(f'<text x="{65+i*100}" y="22" fill="{color}">d = {d}</text>')
        for p in group:
            px, lo, hi = x(p['p']), y(p['interval'][0]), y(p['interval'][1])
            parts.append(f'<path d="M{px:.2f} {lo:.2f} V{hi:.2f} M{px-4:.2f} {lo:.2f} h8 M{px-4:.2f} {hi:.2f} h8" stroke="{color}"/>')
            parts.append(f'<circle cx="{px:.2f}" cy="{y(p["rate"]):.2f}" r="4" fill="{color}"/>')
    parts.append('<text x="350" y="330" text-anchor="middle">Physical noise parameter p</text></svg>')
    return ''.join(parts)


def illustrated_report(project, runs):
    title = escape(project['name'])
    sections = [f'<header><p>QEC LAB · RESEARCH REPORT</p><h1>{title}</h1><p>Snapshot of {len(runs)} investigations · local simulation evidence</p></header>',
                '<h2>Researcher notes</h2><div class="notes">' + escape(project['notes'] or 'No notes recorded.') + '</div>']
    for r in runs:
        spec = r['spec']
        sections.append('<section><h2>' + escape(spec['title']) + '</h2><p>' + escape(spec['question']) + '</p>')
        sections.append('<p>Run ' + escape(r['id']) + ' · ' + escape(r['status']) + ' · ' + escape(r['created']) + '</p>')
        sections.append(f'<p>Rotated surface-code Z memory · {spec["rounds"]} rounds · {escape(spec["decoder"])} MWPM weights · measurement noise {spec["measurement_multiplier"]} × p · seed {spec["seed"]}</p>')
        sections.append(chart(r['points']))
        sections.append('<p>Linear vertical scale: logical error probability per memory experiment. Bars are pointwise 95% Wilson intervals. Lines connect sampled points; they are not threshold fits.</p>')
        sections.append('<table><thead><tr><th>Point</th><th>Failures / shots</th><th>Probability</th><th>95% interval</th><th>Sampling</th></tr></thead><tbody>')
        for p in r['points']:
            sections.append(f'<tr><td>{escape(p["id"])}</td><td>{p["errors"]} / {p["shots"]}</td><td>{p["rate"]:.6g}</td><td>[{p["interval"][0]:.6g}, {p["interval"][1]:.6g}]</td><td>{"Fixed target reached" if p["complete"] else "Provisional"}</td></tr>')
        sections.append('</tbody></table><details><summary>Reproduction environment</summary><pre>' + escape(str(r['environment'])) + '</pre></details></section>')
    sections.append('<footer><h2>Interpretation and reproduction</h2><p>Zero observed failures do not mean zero risk. Partial results are provisional. No sequential or simultaneous confidence coverage is claimed. Finite-distance sweeps alone do not establish an asymptotic threshold. Channel parameter p is not an aggregate hardware error rate. Timing is not hardware latency.</p><p>Download each investigation’s reproduction bundle separately for circuits, decoder models, batch seeds, and replay scripts. This illustrated report is a presentation snapshot, not a reproduction bundle.</p><p>Use your browser’s Print command to print or save this self-contained report as PDF.</p></footer>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '''</title><style>
body{font:15px/1.6 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#243c35}h1{font-size:36px}h2{margin-top:28px}header{border-bottom:3px solid #08786d}section{border-top:1px solid #ddd;margin-top:32px;padding-top:12px}.notes{white-space:pre-wrap}svg{width:100%;max-height:440px}svg text{font:12px system-ui}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}footer{font-size:13px;color:#52645e}@media print{body{margin:0;max-width:none}svg,table{break-inside:avoid}details{display:none}h2{break-after:avoid}}@media(max-width:600px){body{padding:0 12px}td,th{padding:4px;font-size:11px}}
</style><body>''' + ''.join(sections) + '</body></html>'
