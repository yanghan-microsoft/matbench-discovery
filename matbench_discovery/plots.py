from __future__ import annotations

import math
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
import plotly.io as pio
import scipy.interpolate
import scipy.stats
import wandb
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar

from matbench_discovery.energy import classify_stable

__author__ = "Janosh Riebesell"
__date__ = "2022-08-05"

WhichEnergy = Literal["true", "pred"]
AxLine = Literal["x", "y", "xy", ""]
Backend = Literal["matplotlib", "plotly"]

# --- start global plot settings
quantity_labels = dict(
    n_atoms="Atom Count",
    n_elems="Element Count",
    crystal_sys="Crystal system",
    spg_num="Space group",
    n_wyckoff="Number of Wyckoff positions",
    n_sites="Lattice site count",
    energy_per_atom="Energy (eV/atom)",
    e_form="Formation energy (eV/atom)",
    e_above_hull="Energy above convex hull (eV/atom)",
    e_above_hull_pred="Predicted energy above convex hull (eV/atom)",
    e_above_hull_mp="Energy above MP convex hull (eV/atom)",
    e_above_hull_error="Error in energy above convex hull (eV/atom)",
    vol_diff="Volume difference (A^3)",
    e_form_per_atom_mp2020_corrected="Formation energy (eV/atom)",
    e_form_per_atom_pred="Predicted formation energy (eV/atom)",
    material_id="Material ID",
    band_gap="Band gap (eV)",
    formula="Formula",
)
model_labels = dict(
    wren="Wren",
    wrenformer="Wrenformer",
    m3gnet="M3GNet",
    bowsr_megnet="BOWSR + MEGNet",
    cgcnn="CGCNN",
    voronoi="Voronoi",
    wbm="WBM",
    dft="DFT",
)
px.defaults.labels = quantity_labels | model_labels
pastel_layout = dict(
    colorway=px.colors.qualitative.Pastel, margin=dict(l=40, r=30, t=60, b=30)
)
pio.templates["pastel"] = dict(layout=pastel_layout)
pio.templates.default = "plotly_white+pastel"

# https://github.com/plotly/Kaleido/issues/122#issuecomment-994906924
# when seeing MathJax "loading" message in exported PDFs, try:
# pio.kaleido.scope.mathjax = None


plt.rc("font", size=14)
plt.rc("legend", fontsize=16, title_fontsize=16)
plt.rc("axes", titlesize=16, labelsize=16)
plt.rc("savefig", bbox="tight", dpi=200)
plt.rc("figure", dpi=200, titlesize=16)
plt.rcParams["figure.constrained_layout.use"] = True
# --- end global plot settings


def hist_classified_stable_vs_hull_dist(
    e_above_hull_true: pd.Series,
    e_above_hull_pred: pd.Series,
    ax: plt.Axes = None,
    which_energy: WhichEnergy = "true",
    stability_threshold: float = 0,
    x_lim: tuple[float | None, float | None] = (-0.4, 0.4),
    rolling_accuracy: float | None = 0.02,
    backend: Backend = "plotly",
    ylabel: str = "Number of materials",
    **kwargs: Any,
) -> tuple[plt.Axes | go.Figure, dict[str, float]]:
    """
    Histogram of the energy difference (either according to DFT ground truth [default]
    or model predicted energy) to the convex hull for materials in the WBM data set. The
    histogram is broken down into true positives, false negatives, false positives, and
    true negatives based on whether the model predicts candidates to be below the known
    convex hull. Ideally, in discovery setting a model should exhibit high recall, i.e.
    the majority of materials below the convex hull being correctly identified by the
    model.

    See fig. S1 in https://science.org/doi/10.1126/sciadv.abn4117.

    Args:
        e_above_hull_true (pd.Series): Distance to convex hull according to DFT
            ground truth (in eV / atom).
        e_above_hull_pred (pd.Series): Distance to convex hull predicted by model
            (in eV / atom). Same as true energy to convex hull plus predicted minus true
            formation energy.
        ax (plt.Axes, optional): matplotlib axes to plot on.
        which_energy (WhichEnergy, optional): Whether to use the true (DFT) hull
            distance or the model's predicted hull distance for the histogram.
        stability_threshold (float, optional): set stability threshold as distance to
            convex hull in eV/atom, usually 0 or 0.1 eV.
        x_lim (tuple[float | None, float | None]): x-axis limits.
        rolling_accuracy (float): Rolling accuracy window size in eV / atom. Set to None
            or 0 to disable. Defaults to 0.02, meaning 20 meV / atom.
        backend ('matplotlib' | 'plotly'], optional): Which plotting backend to use.
            Changes the return type.
        kwargs: Additional keyword arguments passed to the ax.hist() or px.histogram()
            depending on backend.

    Returns:
        tuple[plt.Axes, dict[str, float]]: plot axes and classification metrics

    NOTE this figure plots hist bars separately which causes aliasing in pdf. Can be
    fixed in Inkscape or similar by merging regions by color.
    """
    true_pos, false_neg, false_pos, true_neg = classify_stable(
        e_above_hull_true, e_above_hull_pred, stability_threshold
    )
    n_true_pos = sum(true_pos)
    n_false_neg = sum(false_neg)

    n_total_pos = n_true_pos + n_false_neg
    null = n_total_pos / len(e_above_hull_true)

    # toggle between histogram of DFT-computed/model-predicted distance to convex hull
    e_above_hull = e_above_hull_true if which_energy == "true" else e_above_hull_pred
    eah_true_pos = e_above_hull[true_pos]
    eah_false_neg = e_above_hull[false_neg]
    eah_false_pos = e_above_hull[false_pos]
    eah_true_neg = e_above_hull[true_neg]
    n_true_pos, n_false_pos, n_true_neg, n_false_neg = map(
        sum, (true_pos, false_pos, true_neg, false_neg)
    )
    # null = (tp + fn) / (tp + tn + fp + fn)
    precision = n_true_pos / (n_true_pos + n_false_pos)

    xlabel = dict(
        true=r"$E_\mathrm{above\ hull}\;\mathrm{(eV / atom)}$",
        pred=r"$E_\mathrm{above\ hull\ pred}\;\mathrm{(eV / atom)}$",
    )[which_energy]
    labels = ["True Positives", "False Negatives", "False Positives", "True Negatives"]

    if backend == "matplotlib":
        ax = ax or plt.gca()
        ax.hist(
            [eah_true_pos, eah_false_neg, eah_false_pos, eah_true_neg],
            bins=200,
            range=x_lim,
            alpha=0.5,
            color=["tab:green", "tab:orange", "tab:red", "tab:blue"],
            label=labels,
            stacked=True,
            **kwargs,
        )
        ax.set(xlabel=xlabel, ylabel=ylabel, xlim=x_lim)

        if stability_threshold is not None:
            ax.axvline(
                stability_threshold,
                color="black",
                linestyle="--",
                label="Stability Threshold",
            )

        if rolling_accuracy:
            # add moving average of the accuracy computed within given window
            # as a function of e_above_hull shown as blue line (right axis)
            ax_acc = ax.twinx()
            ax_acc.set_ylabel("Accuracy", color="darkblue")
            ax_acc.tick_params(labelcolor="darkblue")
            ax_acc.set(ylim=(0, 1))

            # --- moving average of the accuracy
            # compute accuracy within 20 meV/atom intervals
            bins = np.arange(x_lim[0], x_lim[1], rolling_accuracy)
            bin_counts = np.histogram(e_above_hull_true, bins)[0]
            bin_true_pos = np.histogram(eah_true_pos, bins)[0]
            bin_true_neg = np.histogram(eah_true_neg, bins)[0]

            # compute accuracy
            bin_accuracies = (bin_true_pos + bin_true_neg) / bin_counts
            # plot accuracy
            ax_acc.plot(
                bins[:-1],
                bin_accuracies,
                color="tab:blue",
                label="Accuracy",
                linewidth=3,
            )
            # ax2.fill_between(
            #     bin_centers,
            #     bin_accuracy - bin_accuracy_std,
            #     bin_accuracy + bin_accuracy_std,
            #     color="tab:blue",
            #     alpha=0.2,
            # )

    if backend == "plotly":
        clf = (true_pos + false_neg * 2 + false_pos * 3 + true_neg * 4).map(
            dict(zip(range(1, 5), labels))
        )
        df = pd.DataFrame(dict(e_above_hull=e_above_hull, clf=clf))

        ax = px.histogram(
            df,
            x="e_above_hull",
            color="clf",
            nbins=20000,
            range_x=x_lim,
            opacity=0.9,
            **kwargs,
        )
        ax.update_layout(
            dict(xaxis_title=xlabel, yaxis_title=ylabel),
            legend=dict(title=None, yanchor="top", y=1, xanchor="right", x=1),
        )

        if stability_threshold is not None:
            ax.add_vline(stability_threshold, line=dict(dash="dash", width=1))
            ax.add_annotation(
                text="Stability threshold",
                x=stability_threshold,
                y=1.1,
                yref="paper",
                font=dict(size=14, color="gray"),
                showarrow=False,
            )

    recall = n_true_pos / n_total_pos
    return ax, dict(
        enrichment=precision / null,
        precision=precision,
        recall=recall,
        prevalence=null,
        accuracy=(n_true_pos + n_true_neg)
        / (n_true_pos + n_true_neg + n_false_pos + n_false_neg),
        f1=2 * (precision * recall) / (precision + recall),
    )


def rolling_mae_vs_hull_dist(
    e_above_hull_true: pd.Series,
    e_above_hull_pred: pd.Series,
    half_window: float = 0.02,
    bin_width: float = 0.002,
    x_lim: tuple[float, float] = (-0.2, 0.3),
    ax: plt.Axes = None,
    **kwargs: Any,
) -> plt.Axes:
    """Rolling mean absolute error as the energy to the convex hull is varied. A scale
    bar is shown for the windowing period of 40 meV per atom used when calculating
    the rolling MAE. The standard error in the mean is shaded
    around each curve. The highlighted V-shaped region shows the area in which the
    average absolute error is greater than the energy to the known convex hull. This is
    where models are most at risk of misclassifying structures.
    """
    ax = ax or plt.gca()

    is_fresh_ax = len(ax.lines) == 0

    bins = np.arange(*x_lim, bin_width)

    rolling_maes = np.zeros_like(bins)
    rolling_stds = np.zeros_like(bins)
    for idx, bin_center in enumerate(bins):
        low = bin_center - half_window
        high = bin_center + half_window

        mask = (e_above_hull_true <= high) & (e_above_hull_true > low)
        rolling_maes[idx] = e_above_hull_pred.loc[mask].abs().mean()
        rolling_stds[idx] = scipy.stats.sem(e_above_hull_pred.loc[mask].abs())

    kwargs = dict(linewidth=3) | kwargs
    ax.plot(bins, rolling_maes, **kwargs)

    ax.fill_between(
        bins, rolling_maes + rolling_stds, rolling_maes - rolling_stds, alpha=0.3
    )

    if not is_fresh_ax:
        # return earlier if all plot objects besides the line were already drawn by a
        # previous call
        return ax

    scale_bar = AnchoredSizeBar(
        ax.transData,
        2 * half_window,
        "40 meV",
        "lower left",
        pad=0.5,
        frameon=False,
        size_vertical=0.002,
    )
    # indicate size of MAE averaging window
    ax.add_artist(scale_bar)

    # DFT accuracy at 25 meV/atom for relative e_above_hull which is lower than
    # formation energy error due to systematic error cancellation among
    # similar chemistries, supporting ref:
    # https://journals.aps.org/prb/abstract/10.1103/PhysRevB.85.155208
    dft_acc = 0.025
    ax.plot((dft_acc, 1), (dft_acc, 1), color="grey", linestyle="--", alpha=0.3)
    ax.plot((-1, -dft_acc), (1, dft_acc), color="grey", linestyle="--", alpha=0.3)
    ax.plot(
        (-dft_acc, dft_acc), (dft_acc, dft_acc), color="grey", linestyle="--", alpha=0.3
    )
    ax.fill_between(
        (-1, -dft_acc, dft_acc, 1),
        (1, 1, 1, 1),
        (1, dft_acc, dft_acc, 1),
        color="tab:red",
        alpha=0.2,
    )

    ax.plot((0, dft_acc), (0, dft_acc), color="grey", linestyle="--", alpha=0.3)
    ax.plot((-dft_acc, 0), (dft_acc, 0), color="grey", linestyle="--", alpha=0.3)
    ax.fill_between(
        (-dft_acc, 0, dft_acc),
        (dft_acc, dft_acc, dft_acc),
        (dft_acc, 0, dft_acc),
        color="tab:orange",
        alpha=0.2,
    )
    # shrink=0.1 means cut off 10% length from both sides of arrow line
    arrowprops = dict(
        facecolor="black", width=0.5, headwidth=5, headlength=5, shrink=0.1
    )
    ax.annotate(
        xy=(-dft_acc, dft_acc),
        xytext=(-2 * dft_acc, dft_acc),
        text="Corrected\nGGA DFT\nAccuracy",
        arrowprops=arrowprops,
        verticalalignment="center",
        horizontalalignment="right",
    )

    ax.text(0, 0.13, r"$|E_\mathrm{above\ hull}| > $MAE", horizontalalignment="center")
    ax.set(xlabel=r"$E_\mathrm{above\ hull}$ (eV / atom)", ylabel="MAE (eV / atom)")
    ax.set(xlim=x_lim, ylim=(0.0, 0.14))

    return ax


def cumulative_precision_recall(
    e_above_hull_true: pd.Series,
    df_preds: pd.DataFrame,
    stability_threshold: float = 0,  # set stability threshold as distance to convex
    # hull in eV / atom, usually 0 or 0.1 eV
    project_end_point: AxLine = "xy",
    show_optimal: bool = False,
    backend: Backend = "plotly",
    **kwargs: Any,
) -> tuple[plt.Figure | go.Figure, pd.DataFrame]:
    """Create 2 subplots side-by-side with cumulative precision and recall curves for
    all models starting with materials predicted most stable, adding the next material,
    recomputing the cumulative metrics, adding the next most stable material and so on
    until each model no longer predicts the material to be stable. Again, materials
    predicted more stable enter the precision and recall calculation sooner. Different
    models predict different number of materials to be stable. Hence the curves end at
    different points.

    Args:
        e_above_hull_true (pd.Series): Distance to convex hull according to DFT
            ground truth (in eV / atom).
        df_preds (pd.DataFrame): Distance to convex hull predicted by models, one column
            per model (in eV / atom). Same as true energy to convex hull plus predicted
            minus true formation energy.
        stability_threshold (float, optional): Max distance above convex hull before
            material is considered unstable. Defaults to 0.
        project_end_point ('x' | 'y' | 'xy' | '', optional): Whether to project end
        points of precision and recall curves to the x/y axis. Defaults to '', i.e. no
            axis projection lines.
        show_optimal (bool, optional): Whether to plot the optimal recall line. Defaults
            to False.
        backend ('plotly' | 'matplotlib', optional): Defaults to 'plotly'. **kwargs:
        Keyword arguments passed to df.plot().

    Returns:
        tuple[plt.Figure | go.Figure, pd.DataFrame]: The matplotlib/plotly figure and
            dataframe of cumulative metrics for each model.
    """
    fact = lambda: pd.DataFrame(index=range(len(e_above_hull_true)))
    dfs = dict(Precision=fact(), Recall=fact())

    for model_name in df_preds:
        model_preds = df_preds[model_name].sort_values()
        e_above_hull_true = e_above_hull_true.loc[model_preds.index]

        true_pos, false_neg, false_pos, _true_neg = classify_stable(
            e_above_hull_true, model_preds, stability_threshold
        )

        true_pos_cumsum = true_pos.cumsum()
        # precision aka positive predictive value (PPV)
        precision = true_pos_cumsum / (true_pos_cumsum + false_pos.cumsum())
        n_total_pos = sum(true_pos) + sum(false_neg)
        recall = true_pos_cumsum / n_total_pos  # aka true_pos_rate aka sensitivity

        end = int(np.argmax(recall))
        xs = np.arange(end)

        prec_interp = scipy.interpolate.interp1d(xs, precision[:end], kind="cubic")
        recall_interp = scipy.interpolate.interp1d(xs, recall[:end], kind="cubic")
        dfs["Precision"][model_name] = pd.Series(prec_interp(xs))
        dfs["Recall"][model_name] = pd.Series(recall_interp(xs))

    for key, df in dfs.items():
        # drop all-NaN rows so plotly plot x-axis only extends to largest number of
        # predicted materials by any model
        df.dropna(how="all", inplace=True)
        df["metric"] = key

    df_cum = pd.concat(dfs.values())

    if backend == "matplotlib":
        fig, axs = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
        line_kwargs = dict(
            linewidth=3, markevery=[-1], marker="x", markersize=14, markeredgewidth=2.5
        )
        for (key, df), ax in zip(dfs.items(), axs):
            # select every n-th row of df so that 1000 rows are left for increased
            # plotting speed and reduced file size
            # falls back on every row if df has less than 1000 rows

            df.iloc[:: len(df) // 1000 or 1].plot(
                ax=ax, legend=False, backend=backend, **line_kwargs | kwargs, ylabel=key
            )

        # add some visual guidelines
        intersect_kwargs = dict(linestyle=":", alpha=0.4, linewidth=2)
        bbox = dict(facecolor="white", alpha=0.5, edgecolor="none")
        assert len(axs) == len(dfs), f"{len(axs)} != {len(dfs)}"

        for ax, df in zip(axs, dfs.values()):
            ax.set(ylim=(0, 1), xlim=(0, None), ylabel=key)
            for model in df_preds:
                x_end = df[model].dropna().index[-1]
                y_end = df[model].dropna().iloc[-1]
                # place model name at the end of every line
                ax.text(x_end, y_end, model, va="bottom", rotation=30, bbox=bbox)
                if "x" in project_end_point:
                    ax.plot((x_end, x_end), (0, y_end), **intersect_kwargs)
                if "y" in project_end_point:
                    ax.plot((0, x_end), (y_end, y_end), **intersect_kwargs)

        # optimal recall line finds all stable materials without any false positives
        # can be included to confirm all models start out of with near optimal recall
        # and to see how much each model overshoots total n_stable
        n_below_hull = sum(e_above_hull_true < 0)
        if show_optimal:
            opt_label = "Optimal Recall"
            axs[1].plot([0, n_below_hull], [0, 1], color="green", linestyle="--")
            axs[1].text(
                *[n_below_hull, 0.81],
                opt_label,
                color="green",
                va="bottom",
                ha="right",
                rotation=math.degrees(math.cos(math.atan(1 / n_below_hull))),
                bbox=bbox,
            )

    elif backend == "plotly":
        fig = df_cum.iloc[:: len(df_cum) // 1000 or 1].plot(
            backend=backend, facet_col="metric", **kwargs
        )
        fig.update_traces(line=dict(width=4))
        for idx in range(1, 3):
            fig.update_xaxes(
                title_text="Number of materials predicted stable", row=1, col=idx
            )
        fig.update_yaxes(title="Precision", col=1)
        fig.update_yaxes(title="Recall", col=2)
        fig.for_each_annotation(lambda a: a.update(text=""))
        fig.update_layout(legend=dict(title=""))
        fig.update_layout(showlegend=False)

    return fig, df_cum


def wandb_scatter(table: wandb.Table, fields: dict[str, str], **kwargs: Any) -> None:
    """Log a parity scatter plot using custom Vega spec to WandB.

    Args:
        table (wandb.Table): WandB data table.
        fields (dict[str, str]): Map from table columns to fields defined in the custom
            vega spec. Currently the only Vega fields are 'x' and 'y'.
        **kwargs: Keyword arguments passed to wandb.plot_table(string_fields=kwargs).
    """
    assert set(fields) >= {"x", "y"}, f"{fields=} must specify x and y column names"

    if "form" in fields["x"] and "form" in fields["y"]:
        kwargs.setdefault("x_label", "DFT formation energy (eV/atom)")
        kwargs.setdefault("y_label", "Predicted formation energy (eV/atom)")

    scatter_plot = wandb.plot_table(
        vega_spec_name="janosh/scatter-parity",
        data_table=table,
        fields=fields,
        string_fields=kwargs,
    )

    wandb.log({"true_pred_scatter": scatter_plot})
