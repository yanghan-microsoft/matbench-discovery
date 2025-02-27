"""parity plot of actual vs predicted e_above_hull and e_form_per_atom for all
models. First 2 plots put all models in single figure with selectable traces.
Last plot is split into 2x3 subplots, one for each model.
"""

# %%
import math
from typing import Literal

import numpy as np
import plotly.express as px
from pymatviz.io import save_fig
from pymatviz.powerups import add_identity_line
from pymatviz.utils import bin_df_cols

from matbench_discovery import PDF_FIGS, SITE_FIGS
from matbench_discovery.enums import Key, TestSubset
from matbench_discovery.plots import clf_colors
from matbench_discovery.preds import df_metrics, df_metrics_uniq_protos, df_preds

__author__ = "Janosh Riebesell"
__date__ = "2022-11-28"

legend = dict(x=1, y=0, xanchor="right", yanchor="bottom", title=None)

# toggle between formation energy and energy above convex hull
which_energy: Literal["e-form", "each"] = globals().get("which_energy", "each")
if which_energy == "each":
    e_pred_col = Key.each_pred
    e_true_col = Key.each_true
else:
    assert which_energy == "e-form", f"Invalid {which_energy=}"
    e_true_col = Key.e_form
    e_pred_col = Key.e_form_pred


test_subset = globals().get("test_subset", TestSubset.full)

if test_subset == TestSubset.uniq_protos:
    df_preds = df_preds.query(Key.uniq_proto)
    df_metrics = df_metrics_uniq_protos


# %%
facet_col = "Model"
hover_cols = (Key.each_true, Key.formula)
models = list(df_metrics.T.MAE.nsmallest(6).index)  # top 6 models by MAE
models = list(df_metrics)  # all models

df_melt = df_preds.melt(
    id_vars=(df_preds.index.name, Key.e_form, *hover_cols),
    var_name=facet_col,
    value_vars=models,
    value_name=Key.e_form_pred,
)

df_melt[Key.each_pred] = (
    df_melt[Key.each_true] + df_melt[Key.e_form_pred] - df_melt[Key.e_form]
)

df_bin = bin_df_cols(
    df_melt,
    bin_by_cols=[e_true_col, e_pred_col],
    group_by_cols=[facet_col],
    n_bins=300,
    bin_counts_col=(bin_cnt_col := "bin counts"),
)
df_bin = df_bin.reset_index()

# sort legend and facet plots by MAE
legend_order = list(df_metrics.T.MAE.sort_values().index)


# determine each point's classification to color them by
# now unused, can be used to color points by TP/FP/TN/FN
# true_pos, false_neg, false_pos, true_neg = classify_stable(
#     df_bin[e_true_col], df_bin[e_pred_col]
# )
# clf_col = "classified"
# df_bin[clf_col] = np.array(clf_labels)[
#     true_pos * 0 + false_neg * 1 + false_pos * 2 + true_neg * 3
# ]


# %% parity plot of actual vs predicted e_form_per_atom
fig = px.scatter(
    df_bin,
    x=Key.e_form,
    y=Key.e_form_pred,
    color=facet_col,
    hover_data=hover_cols,
    hover_name=df_preds.index.name,
    opacity=0.7,
    category_orders={facet_col: legend_order},
)

for trace in fig.data:
    # initially hide all traces, let users select which models to compare
    trace.visible = "legendonly"
    model = trace.name
    assert model in df_preds, f"Unexpected {model=} not in {models}"
    MAE, R2 = df_metrics[model][["MAE", "R2"]]
    trace.name = f"{model} · {MAE=:.2f} · R<sup>2</sup>={R2:.2f}"

fig.update_layout(legend=legend)
add_identity_line(fig)
fig.show()

img_name = f"{SITE_FIGS}/e-form-parity-models"
# save_fig(fig, f"{img_path}.svelte")


# %% parity plot of actual vs predicted e_above_hull
fig = px.scatter(
    df_bin,
    x=e_true_col,
    y=e_pred_col,
    color=facet_col,
    hover_data=hover_cols,
    hover_name=df_preds.index.name,
    opacity=0.7,
    category_orders={facet_col: legend_order},
)

for trace in fig.data:
    trace.visible = "legendonly"
    model = trace.name
    assert model in df_preds, f"Unexpected {model=} not in {models}"
    MAE, R2 = df_metrics[model][["MAE", "R2"]]
    trace.name = f"{model} · {MAE=:.2f} · R<sup>2</sup>={R2:.2f}"

fig.update_layout(legend=legend)
add_identity_line(fig)
fig.show()

img_name = f"{SITE_FIGS}/e-above-hull-parity-models"
# save_fig(fig, f"{img_path}.svelte")


# %% parity plot of DFT vs predicted hull distance with each model in separate subplot
log_bin_cnt_col = f"log {bin_cnt_col}"
df_bin[log_bin_cnt_col] = np.log1p(df_bin[bin_cnt_col]).round(2)

n_cols = 4
n_rows = math.ceil(len(models) / n_cols)

fig = px.scatter(
    df_bin,
    x=e_true_col,
    y=e_pred_col,
    facet_col=facet_col,
    facet_col_wrap=n_cols,
    color=log_bin_cnt_col,
    facet_col_spacing=0.02,
    facet_row_spacing=0.04,
    hover_data=hover_cols,
    hover_name=df_preds.index.name,
    # color=clf_col,
    # color_discrete_map=clf_color_map,
    # opacity=0.4,
    range_x=(domain := (-4, 7) if which_energy == "each" else (-6, 6)),
    range_y=domain,
    category_orders={facet_col: legend_order},
    # pick from https://plotly.com/python/builtin-colorscales
    color_continuous_scale="agsunset",
)
# decrease marker size
fig.update_traces(marker=dict(size=2))
# manually set colorbar ticks and labels (needed after log1p transform)
tick_vals = [1, 10, 100, 1000, 10_000]
fig.layout.coloraxis.colorbar.update(
    tickvals=np.log1p(tick_vals), ticktext=list(map(str, tick_vals))
)

x_title = fig.layout.xaxis.title.text  # used in annotations below
y_title = fig.layout.yaxis.title.text

# iterate over subplots and set new title
for idx, anno in enumerate(fig.layout.annotations, start=1):
    traces = [t for t in fig.data if t.xaxis == f"x{idx if idx > 1 else ''}"]
    # assert len(traces) in (0, 4), f"Plots must have 0 or 4 traces, got {len(traces)=}"

    model = anno.text.split("=", 1)[1]
    assert model in df_preds, f"Unexpected {model=} not in {list(df_preds)=}"
    # add MAE and R2 to subplot titles
    MAE, R2 = df_metrics[model][["MAE", "R2"]]
    sub_title = f"{model} · {MAE=:.2f} · R<sup>2</sup>={R2:.2f}"
    fig.layout.annotations[idx - 1].text = sub_title

    # remove subplot x and y axis titles
    fig.layout[f"xaxis{idx}"].title.text = ""
    fig.layout[f"yaxis{idx}"].title.text = ""

# add transparent rectangle with TN, TP, FN, FP labels in each quadrant
if e_true_col == Key.each_true:
    # add dashed quadrant separators
    fig.add_vline(x=0, line=dict(width=0.5, dash="dash"))
    fig.add_hline(y=0, line=dict(width=0.5, dash="dash"))

    for sign_x, sign_y, label, color in (
        (-1, -1, "TP", clf_colors[0]),
        (-1, 1, "FN", clf_colors[1]),
        (1, -1, "FP", clf_colors[2]),
        (1, 1, "TN", clf_colors[3]),
    ):
        # instead of coloring points in each quadrant, we can add a transparent
        # background to each quadrant (looks worse maybe than coloring points)
        # fig.add_shape(
        #     type="rect",
        #     x0=0,
        #     y0=0,
        #     x1=sign_x * 100,
        #     y1=sign_y * 100,
        #     fillcolor=color,
        #     opacity=0.2,
        #     layer="below",
        #     row="all",
        #     col="all",
        # )
        fig.add_annotation(
            x=(domain[0] if sign_x < 0 else domain[1]),
            y=(domain[0] if sign_y < 0 else domain[1]),
            xshift=-20 * sign_x,
            yshift=-15 * sign_y,
            text=label,
            showarrow=False,
            font=dict(size=14, color=color),
            row="all",
            col="all",
        )

# enable grid
fig.update_layout(
    xaxis=dict(showgrid=True),
    yaxis=dict(showgrid=True),
)

fig.update_xaxes(nticks=8)
fig.update_yaxes(nticks=8)
add_identity_line(fig)

# remove legend title and place legend centered above subplots, increase marker size
fig.layout.legend.update(
    title="", orientation="h", x=0.5, xanchor="center", y=1.15, itemsizing="constant"
)

# fig.update_layout(yaxis=dict(scaleanchor="x", scaleratio=1))

axis_titles = dict(xref="paper", yref="paper", showarrow=False)
portrait = n_rows > n_cols
fig.add_annotation(  # x-axis title
    x=0.5,
    y=-0.06 if portrait else -0.18,
    text=x_title,
    **axis_titles,
)
fig.add_annotation(  # y-axis title
    x=-0.07,
    y=0.5,
    text=y_title,
    textangle=-90,
    **axis_titles,
)

fig.layout.update(height=230 * n_rows, width=240 * n_cols)
fig.layout.coloraxis.colorbar.update(orientation="h", thickness=9, len=0.5, y=1.05)
# fig.layout.width = 1100
fig.layout.margin.update(l=40, r=10, t=30 if portrait else 10, b=60 if portrait else 10)
fig.update_xaxes(matches=None)
fig.update_yaxes(matches=None)
fig.show()


# %%
fig_name = f"{which_energy}-parity-models-{n_rows}x{n_cols}"
save_fig(fig, f"{SITE_FIGS}/{fig_name}.svelte")
save_fig(fig, f"{PDF_FIGS}/{fig_name}.pdf")
