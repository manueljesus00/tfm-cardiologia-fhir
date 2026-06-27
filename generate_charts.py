"""
generate_charts.py — Generación de gráficas para el Capítulo 5 del TFM.

Uso:
    python generate_charts.py

Salida: data/graficas/g1_*.png ... g8_*.png
"""
import csv
import warnings
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

warnings.filterwarnings('ignore')

# ── Configuración ──────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("data/graficas")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 150
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'axes.titlepad': 12,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
})

# Paleta académica accesible
COLOR_OK    = "#2E86AB"
COLOR_FAIL  = "#E84855"
COLOR_TO    = "#F4A261"
COLOR_NONE  = "#CCCCCC"

# Orden canónico y etiquetas cortas de modelos
MODEL_ORDER = [
    "Gemini 3.1 Flash Lite",
    "Groq/llama-3.3-70b-versatile",
    "Groq/llama-3.1-8b-instant",
    "Ollama/phi4-mini",
    "Ollama/llama3.2:3b",
    "Ollama/gemma3:4b",
    "Ollama/qwen2.5:7b",
    "Ollama/meditron:7b",
    "Ollama/medllama2:latest",
    "Ollama/cniongolo/biomistral:latest",
]

MODEL_LABELS = {
    "Gemini 3.1 Flash Lite":               "Gemini\nFlash Lite",
    "Groq/llama-3.3-70b-versatile":        "Groq\nLlama-3.3-70B",
    "Groq/llama-3.1-8b-instant":           "Groq\nLlama-3.1-8B",
    "Ollama/phi4-mini":                    "Phi4-mini\n(local)",
    "Ollama/llama3.2:3b":                  "Llama3.2-3B\n(local)",
    "Ollama/gemma3:4b":                    "Gemma3-4B\n(local)",
    "Ollama/qwen2.5:7b":                   "Qwen2.5-7B\n(local)",
    "Ollama/meditron:7b":                  "Meditron-7B\n(local)",
    "Ollama/medllama2:latest":             "Medllama2\n(local)",
    "Ollama/cniongolo/biomistral:latest":  "Biomistral\n(local)",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_csv(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def deduplicate(rows: list[dict], key_fields: list[str]) -> list[dict]:
    """Conserva la fila más reciente por combinación de claves."""
    seen = {}
    for row in sorted(rows, key=lambda r: r.get('timestamp', '')):
        key = tuple(row[f] for f in key_fields)
        seen[key] = row
    return list(seen.values())

def lbl(m: str) -> str:
    return MODEL_LABELS.get(m, m)

def success_rate(rows: list[dict], modelo: str) -> float:
    sub = [r for r in rows if r['modelo'] == modelo]
    if not sub:
        return 0.0
    return 100 * sum(1 for r in sub if r['exito'] == 'True') / len(sub)

def mean_field(rows: list[dict], modelo: str, field: str, nonzero: bool = True) -> float:
    sub = [r for r in rows if r['modelo'] == modelo]
    vals = [float(r[field]) for r in sub if r.get(field)]
    if nonzero:
        vals = [v for v in vals if v > 0]
    return sum(vals) / len(vals) if vals else 0.0

def save(fig, name: str):
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"  [✓] {name}")

def short_doc(filename: str) -> str:
    """Extrae etiqueta corta de un nombre de archivo FHIR."""
    s = filename
    for suffix in ['_gemini-3.1-flash-lite_fhir.json', '_gemini-2.5-flash_fhir.json', '_fhir.json']:
        s = s.replace(suffix, '')
    parts = s.split('_')
    if s.startswith('inf_') or s.startswith('S0'):
        return s[:12]
    # A_01_HTA_Diaz_Cristina → HTA\nDiaz C.
    if len(parts) >= 4:
        patologia = parts[2]
        apellido  = parts[3]
        return f"{patologia}\n{apellido}"
    if len(parts) >= 3:
        return f"{parts[1]}\n{parts[2]}"
    return s[:12]

# ── Carga y deduplicación ──────────────────────────────────────────────────────
print("Cargando datos...")
f1_raw = load_csv("data/benchmark_fase1.csv")
f2_raw = load_csv("data/benchmark_fase2.csv")

f1 = deduplicate(f1_raw, ['archivo', 'modelo'])
f2 = deduplicate(f2_raw, ['archivo', 'modelo'])

models = [m for m in MODEL_ORDER if any(r['modelo'] == m for r in f1 + f2)]

print(f"  F1: {len(f1)} filas únicas | F2: {len(f2)} filas únicas")
print("\nGenerando gráficas...")

# ══════════════════════════════════════════════════════════════════════════════
# G1 — Tasa de éxito F1 vs F2 (barras agrupadas)
# ══════════════════════════════════════════════════════════════════════════════
rates_f1 = [success_rate(f1, m) for m in models]
rates_f2 = [success_rate(f2, m) for m in models]

fig, ax = plt.subplots(figsize=(13, 6))
x = np.arange(len(models))
w = 0.38

bars1 = ax.bar(x - w/2, rates_f1, w, label='Fase 1 — NER + FHIR', color=COLOR_OK, alpha=0.88)
bars2 = ax.bar(x + w/2, rates_f2, w, label='Fase 2 — CIE-10-ES',  color='#E8A838', alpha=0.88)

ax.set_ylabel('Tasa de éxito (%)', fontsize=12)
ax.set_title('Tasa de éxito por modelo en cada fase del pipeline', fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([lbl(m) for m in models], fontsize=8.5)
ax.set_ylim(0, 118)
ax.axhline(100, color='gray', linewidth=0.8, linestyle='--', alpha=0.4)
ax.legend(fontsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

for bar in list(bars1) + list(bars2):
    h = bar.get_height()
    if h > 0:
        ax.text(bar.get_x() + bar.get_width() / 2, h + 1.5,
                f'{h:.0f}%', ha='center', va='bottom', fontsize=7.5, fontweight='bold')

save(fig, "g1_tasa_exito_f1_f2.png")

# ══════════════════════════════════════════════════════════════════════════════
# G2 — Tiempo de respuesta F1 (barras horizontales, escala log)
# ══════════════════════════════════════════════════════════════════════════════
times_f1 = [mean_field(f1, m, 'tiempo_s', nonzero=False) for m in models]

bar_colors = []
for m in models:
    sub = [r for r in f1 if r['modelo'] == m]
    has_ok = any(r['exito'] == 'True' for r in sub)
    has_to = any(r['timeout_ocurrido'] == 'True' for r in sub)
    if has_ok:
        bar_colors.append(COLOR_OK)
    elif has_to:
        bar_colors.append(COLOR_TO)
    else:
        bar_colors.append(COLOR_FAIL)

fig, ax = plt.subplots(figsize=(11, 6))
models_rev  = list(reversed(models))
times_rev   = list(reversed(times_f1))
colors_rev  = list(reversed(bar_colors))

ax.barh([lbl(m) for m in models_rev],
        [max(t, 0.5) for t in times_rev],
        color=colors_rev, alpha=0.88, edgecolor='white')

ax.set_xscale('log')
ax.axvline(120, color=COLOR_FAIL, linewidth=1.8, linestyle='--', zorder=5)
ax.axvline(10,  color='#555555',  linewidth=1.2, linestyle=':',  alpha=0.6, zorder=5)
ax.text(122, 0.3, 'Timeout\n120 s', fontsize=8, color=COLOR_FAIL, va='bottom')
ax.text(10.5, 0.3, '10 s',           fontsize=8, color='#555555', va='bottom')
ax.set_xlabel('Tiempo medio por documento (s) — escala logarítmica', fontsize=11)
ax.set_title('Fase 1: Tiempo de respuesta medio por modelo', fontsize=13, fontweight='bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

patches = [
    mpatches.Patch(color=COLOR_OK,   label='Exitoso'),
    mpatches.Patch(color=COLOR_TO,   label='Timeout sistemático'),
    mpatches.Patch(color=COLOR_FAIL, label='Fallo de formato'),
]
ax.legend(handles=patches, fontsize=9, loc='lower right')

save(fig, "g2_tiempo_respuesta_f1.png")

# ══════════════════════════════════════════════════════════════════════════════
# G3 — Throughput tokens/s F1 vs F2 (barras agrupadas)
# ══════════════════════════════════════════════════════════════════════════════
tps_f1 = [mean_field(f1, m, 'tokens_por_segundo') for m in models]
tps_f2 = [mean_field(f2, m, 'tokens_por_segundo') for m in models]

fig, ax = plt.subplots(figsize=(13, 6))
bars1 = ax.bar(x - w/2, tps_f1, w, label='Fase 1', color=COLOR_OK,    alpha=0.88)
bars2 = ax.bar(x + w/2, tps_f2, w, label='Fase 2', color='#E8A838', alpha=0.88)

ax.set_ylabel('Tokens por segundo (tok/s)', fontsize=12)
ax.set_title('Throughput por modelo (tokens/s) — Fase 1 vs Fase 2', fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([lbl(m) for m in models], fontsize=8.5)
ax.legend(fontsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

for bar in list(bars1) + list(bars2):
    h = bar.get_height()
    if h > 5:
        ax.text(bar.get_x() + bar.get_width() / 2, h + 8,
                f'{h:.0f}', ha='center', va='bottom', fontsize=7)

save(fig, "g3_throughput_f1_f2.png")

# ══════════════════════════════════════════════════════════════════════════════
# G4 — Distribución resultados F2 (barras apiladas %)
# ══════════════════════════════════════════════════════════════════════════════
def f2_breakdown(rows, modelo):
    sub = [r for r in rows if r['modelo'] == modelo]
    ok  = sum(1 for r in sub if r['exito'] == 'True')
    to  = sum(1 for r in sub if r['timeout_ocurrido'] == 'True')
    err = sum(1 for r in sub if r['exito'] == 'False' and r['timeout_ocurrido'] == 'False')
    return ok, to, err

breakdowns = [f2_breakdown(f2, m) for m in models]
totals  = [sum(b) for b in breakdowns]
oks_p   = [100 * b[0] / t if t else 0 for b, t in zip(breakdowns, totals)]
tos_p   = [100 * b[1] / t if t else 0 for b, t in zip(breakdowns, totals)]
errs_p  = [100 * b[2] / t if t else 0 for b, t in zip(breakdowns, totals)]
bot_to  = oks_p
bot_err = [o + t for o, t in zip(oks_p, tos_p)]

fig, ax = plt.subplots(figsize=(13, 6))
ax.bar(x, oks_p,  w * 2.1, label='Éxito',       color=COLOR_OK,   alpha=0.88)
ax.bar(x, tos_p,  w * 2.1, label='Timeout',      color=COLOR_TO,   alpha=0.88, bottom=bot_to)
ax.bar(x, errs_p, w * 2.1, label='Error JSON',   color=COLOR_FAIL, alpha=0.88, bottom=bot_err)

ax.set_ylabel('Distribución de resultados (%)', fontsize=12)
ax.set_title('Fase 2: Distribución de resultados por modelo', fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([lbl(m) for m in models], fontsize=8.5)
ax.set_ylim(0, 115)
ax.legend(fontsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

save(fig, "g4_resultados_f2_apilado.png")

# ══════════════════════════════════════════════════════════════════════════════
# G5 — Scatter: tiempo medio vs tasa resolución F2
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 7))

for m in models:
    sub = [r for r in f2 if r['modelo'] == m]
    if not sub:
        continue
    t_med  = sum(float(r['tiempo_s']) for r in sub) / len(sub)
    tasa   = 100 * sum(1 for r in sub if r['exito'] == 'True') / len(sub)
    tokens = sum(int(r.get('tokens_total') or 0) for r in sub) / len(sub)
    size   = max(80, tokens / 4)
    has_to = any(r['timeout_ocurrido'] == 'True' for r in sub)

    if tasa == 100:
        col = COLOR_OK
    elif has_to:
        col = COLOR_TO
    else:
        col = COLOR_FAIL

    ax.scatter(t_med, tasa, s=size, color=col, alpha=0.78,
               edgecolors='white', linewidth=1.0, zorder=3)
    ax.annotate(lbl(m), (t_med, tasa), fontsize=7.5, ha='left', va='bottom',
                xytext=(5, 5), textcoords='offset points')

ax.set_xlabel('Tiempo medio por documento (s)', fontsize=11)
ax.set_ylabel('Tasa de resolución (%)', fontsize=11)
ax.set_title('Fase 2: Tiempo de respuesta vs. Calidad de codificación\n'
             '(tamaño de burbuja ∝ tokens consumidos por llamada)',
             fontsize=12, fontweight='bold')
ax.set_ylim(-8, 118)
ax.axhline(100, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

patches = [
    mpatches.Patch(color=COLOR_OK,   label='100% resolución'),
    mpatches.Patch(color=COLOR_FAIL, label='0% resolución (error JSON)'),
    mpatches.Patch(color=COLOR_TO,   label='0% resolución (timeout)'),
]
ax.legend(handles=patches, fontsize=9)

save(fig, "g5_scatter_tiempo_calidad_f2.png")

# ══════════════════════════════════════════════════════════════════════════════
# G6 — Heatmap modelo × documento (F2)
# ══════════════════════════════════════════════════════════════════════════════
from matplotlib.colors import ListedColormap

docs_f2 = sorted(set(r['archivo'] for r in f2))
doc_labels_short = [short_doc(d) for d in docs_f2]

# Matriz: MODEL_ORDER × docs_f2
matrix = np.full((len(MODEL_ORDER), len(docs_f2)), -1.0)
for i, m in enumerate(MODEL_ORDER):
    for j, doc in enumerate(docs_f2):
        sub = [r for r in f2 if r['modelo'] == m and r['archivo'] == doc]
        if not sub:
            matrix[i, j] = -1   # sin datos
        elif any(r['exito'] == 'True' for r in sub):
            matrix[i, j] = 2    # éxito
        elif any(r['timeout_ocurrido'] == 'True' for r in sub):
            matrix[i, j] = 1    # timeout
        else:
            matrix[i, j] = 0    # error

# Normalizar a índices 0-3 para el colormap
matrix_idx = np.where(matrix == -1, 0,
             np.where(matrix == 0,   1,
             np.where(matrix == 1,   2, 3)))

cmap_hm = ListedColormap([COLOR_NONE, COLOR_FAIL, COLOR_TO, COLOR_OK])

fig, ax = plt.subplots(figsize=(15, 5))
ax.imshow(matrix_idx, cmap=cmap_hm, vmin=0, vmax=3, aspect='auto')

ax.set_xticks(range(len(docs_f2)))
ax.set_xticklabels(doc_labels_short, rotation=40, ha='right', fontsize=7.5)
ax.set_yticks(range(len(MODEL_ORDER)))
ax.set_yticklabels([lbl(m) for m in MODEL_ORDER], fontsize=8.5)
ax.set_title('Fase 2: Mapa de resultados por modelo × documento FHIR',
             fontsize=12, fontweight='bold')

# Grid lines entre celdas
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_xticks(np.arange(-0.5, len(docs_f2), 1), minor=True)
ax.set_yticks(np.arange(-0.5, len(MODEL_ORDER), 1), minor=True)
ax.grid(which='minor', color='white', linewidth=1.5)
ax.tick_params(which='minor', size=0)

patches = [
    mpatches.Patch(color=COLOR_NONE, label='Sin datos'),
    mpatches.Patch(color=COLOR_FAIL, label='Error JSON'),
    mpatches.Patch(color=COLOR_TO,   label='Timeout'),
    mpatches.Patch(color=COLOR_OK,   label='Éxito'),
]
ax.legend(handles=patches, fontsize=8.5, loc='upper right',
          bbox_to_anchor=(1.0, -0.18), ncol=4)

plt.tight_layout()
save(fig, "g6_heatmap_modelo_documento.png")

# ══════════════════════════════════════════════════════════════════════════════
# G7 — Distribución nivel de confianza NER (F1, solo modelos exitosos)
# ══════════════════════════════════════════════════════════════════════════════
conf_map = {
    'high':    ('Alta',    '#2E86AB'),
    'medium':  ('Media',   '#4ECDC4'),
    'low':     ('Baja',    '#FFD166'),
    'minimal': ('Mínima',  '#F4A261'),
    '':        ('Sin nivel','#CCCCCC'),
}

models_ok_f1 = ["Gemini 3.1 Flash Lite", "Groq/llama-3.3-70b-versatile"]

fig, axes = plt.subplots(1, 2, figsize=(11, 5))
fig.suptitle('Fase 1: Distribución del nivel de confianza de extracción NER\n'
             '(modelos exitosos)', fontsize=12, fontweight='bold')

for ax, m in zip(axes, models_ok_f1):
    sub = [r for r in f1 if r['modelo'] == m]
    counts = defaultdict(int)
    for r in sub:
        counts[r.get('confidence_level', '') or ''] += 1

    sizes, labels_pie, colors_pie = [], [], []
    for key in ['high', 'medium', 'low', 'minimal', '']:
        v = counts.get(key, 0)
        if v > 0:
            lbl_text, col = conf_map[key]
            sizes.append(v)
            labels_pie.append(f"{lbl_text} ({v})")
            colors_pie.append(col)

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels_pie, colors=colors_pie,
        autopct='%1.0f%%', startangle=90,
        textprops={'fontsize': 9}, pctdistance=0.75
    )
    ax.set_title(lbl(m), fontsize=10, fontweight='bold', pad=10)

save(fig, "g7_confianza_ner_f1.png")

# ══════════════════════════════════════════════════════════════════════════════
# G8 — Distribución de códigos CIE-10-ES asignados
# ══════════════════════════════════════════════════════════════════════════════
chapter_colors = {
    'I': ('#C1121F', 'Cap. IX — Circulatorio'),
    'E': ('#E07A5F', 'Cap. IV — Endocrino'),
    'G': ('#3D405B', 'Cap. VI — Nervioso'),
    'Z': ('#81B29A', 'Cap. XXI — Factores salud'),
    'D': ('#F2CC8F', 'Cap. III — Sangre/inmune'),
    'M': ('#2E86AB', 'Cap. XIII — Musculoesquelético'),
}

cie_counts = defaultdict(int)
for r in f2:
    if r['exito'] == 'True' and r.get('cie10_codes'):
        for code in r['cie10_codes'].split(','):
            code = code.strip()
            if code:
                cie_counts[code] += 1

codes_sorted = sorted(cie_counts.items(), key=lambda x: -x[1])
codes  = [c for c, _ in codes_sorted]
counts = [v for _, v in codes_sorted]
bar_colors_cie = [chapter_colors.get(c[0], ('#CCCCCC', 'Otro'))[0] for c in codes]

fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.barh(codes, counts, color=bar_colors_cie, alpha=0.88, edgecolor='white', height=0.6)

for bar, cnt in zip(bars, counts):
    ax.text(cnt + 0.3, bar.get_y() + bar.get_height() / 2,
            str(cnt), va='center', fontsize=9)

ax.set_xlabel('Número de asignaciones (todos los modelos exitosos)', fontsize=11)
ax.set_title('Distribución de códigos CIE-10-ES asignados en Fase 2',
             fontsize=13, fontweight='bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.invert_yaxis()

seen_chapters = set(c[0] for c in codes)
patches = [
    mpatches.Patch(color=chapter_colors[ch][0], label=chapter_colors[ch][1])
    for ch in chapter_colors if ch in seen_chapters
]
ax.legend(handles=patches, fontsize=8.5, title='Capítulo CIE-10', title_fontsize=9)

save(fig, "g8_distribucion_cie10.png")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n✅ 8 gráficas guardadas en '{OUTPUT_DIR}/'")
print("\nUbicación recomendada en el TFM:")
print("  g1_tasa_exito_f1_f2.png       → §5.3.1 (inicio, visión global)")
print("  g2_tiempo_respuesta_f1.png    → §5.4.1 (tiempo de respuesta F1)")
print("  g3_throughput_f1_f2.png       → §5.4.1 (throughput comparativo)")
print("  g4_resultados_f2_apilado.png  → §5.3.1 (tabla resultados F2)")
print("  g5_scatter_tiempo_calidad.png → §5.4.2 (calidad vs tiempo)")
print("  g6_heatmap_modelo_documento.png → §5.3.2 (resultados pipeline)")
print("  g7_confianza_ner_f1.png       → §5.4.2 (calidad extracción NER)")
print("  g8_distribucion_cie10.png     → §5.3.2 (códigos asignados)")
