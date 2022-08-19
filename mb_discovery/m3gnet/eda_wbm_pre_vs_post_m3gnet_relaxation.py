# %%
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.io as pio
from pymatgen.core import Structure
from pymatgen.util.coord import pbc_diff
from pymatviz.utils import add_identity_line

from mb_discovery import ROOT


__author__ = "Janosh Riebesell"
__date__ = "2022-06-18"


pio.templates.default = "plotly_white"

today = f"{datetime.now():%Y-%m-%d}"


# %%
df_wbm = pd.read_json(
    f"{ROOT}/data/2022-06-26-wbm-cses-and-initial-structures.json.gz"
).set_index("material_id")


# %%
df_m3gnet = pd.read_json(
    f"{ROOT}/data/2022-08-16-m3gnet-wbm-relax-results.json.gz"
).set_index("material_id")

print("Number of WBM crystals for which we have M3GNet results:")
print(f"{len(df_m3gnet):,} / {len(df_wbm):,} = {len(df_m3gnet)/len(df_wbm):.1%}")


# %% spread M3GNet post-pseudo-relaxation lattice params into separate columns
df_m3gnet["final_energy"] = df_m3gnet.trajectory.map(lambda x: x["energies"][-1][0])

df_m3gnet_lattice = pd.json_normalize(
    df_m3gnet.initial_structure.map(lambda x: x["lattice"])
).add_prefix("m3gnet_")
df_m3gnet[df_m3gnet_lattice.columns] = df_m3gnet_lattice.to_numpy()
df_m3gnet


# %% spread WBM initial and final lattice params into separate columns
df_m3gnet["final_wbm_structure"] = df_wbm.cse.map(lambda x: x["structure"])
df_wbm_final_lattice = pd.json_normalize(
    df_m3gnet.final_wbm_structure.map(lambda x: x["lattice"])
).add_prefix("final_wbm_")
df_m3gnet[df_wbm_final_lattice.columns] = df_wbm_final_lattice.to_numpy()


df_m3gnet["initial_wbm_structure"] = df_wbm.initial_structure
df_wbm_initial_lattice = pd.json_normalize(
    df_m3gnet.initial_structure.map(lambda x: x["lattice"])
).add_prefix("initial_wbm_")
df_m3gnet[df_wbm_initial_lattice.columns] = df_wbm_initial_lattice.to_numpy()


# %%
df_wbm_final_lattice = pd.json_normalize(
    df_wbm.cse.map(lambda x: x["structure"]["lattice"])
).add_prefix("final_wbm_")
df_wbm = df_wbm.join(df_wbm_final_lattice)

df_wbm_initial_lattice = pd.json_normalize(
    df_wbm.initial_structure.map(lambda x: x["lattice"])
).add_prefix("initial_wbm_")
df_wbm[df_wbm_initial_lattice.columns] = df_wbm_initial_lattice.to_numpy()

print(f"{df_wbm.isna().sum()=}")

df_wbm.query("initial_wbm_matrix.isna()")


# %%
px.histogram(
    df_m3gnet.filter(like="volume"),
    nbins=500,
    barmode="overlay",
    opacity=0.5,
    range_x=[0, 500],
)


# %%
fig = px.scatter(
    df_m3gnet.round(1),
    x="final_wbm_volume",
    y=["initial_wbm_volume", "m3gnet_volume"],
    hover_data=[df_m3gnet.index],
)
add_identity_line(fig)
fig.update_layout(
    title="Slightly tighter spread of M3GNet-relaxed vs initial WBM volumes"
)
fig.show()


# %% histogram of alpha lattice angles (similar results for beta and gamma)
fig = px.histogram(
    df_m3gnet.filter(like="alpha"), nbins=1000, barmode="overlay", log_y=True
)
fig.show()


# %%
px.histogram(
    df_m3gnet.filter(regex="_c$"),
    nbins=1000,
    log_y=True,
    barmode="overlay",
    opacity=0.5,
)


# %%
df_m3gnet["final_m3gnet_structure"] = df_m3gnet.final_structure.map(Structure.from_dict)
df_m3gnet["initial_wbm_structure"] = df_m3gnet.initial_wbm_structure.map(
    Structure.from_dict
)
df_m3gnet["final_wbm_structure"] = df_m3gnet.final_wbm_structure.map(
    Structure.from_dict
)


df_m3gnet["m3gnet_pbc_diffs"] = [
    abs(
        pbc_diff(
            row.initial_wbm_structure.frac_coords,
            row.final_m3gnet_structure.frac_coords,
        )
    ).mean()
    for row in df_m3gnet.itertuples()
]


df_m3gnet["wbm_pbc_diffs"] = [
    abs(
        pbc_diff(
            row.initial_wbm_structure.frac_coords,
            row.final_wbm_structure.frac_coords,
        )
    ).mean()
    for row in df_m3gnet.itertuples()
]

df_m3gnet["m3gnet_to_final_wbm_pbc_diffs"] = [
    abs(
        pbc_diff(
            row.final_m3gnet_structure.frac_coords,
            row.final_wbm_structure.frac_coords,
        )
    ).mean()
    for row in df_m3gnet.itertuples()
]


print(
    "mean PBC difference of fractional coordinates before vs after relaxation with WBM "
    "and M3GNet"
)

wbm_pbc_diffs_mean = df_m3gnet.wbm_pbc_diffs.mean()
print(f"{wbm_pbc_diffs_mean = :.3}")

m3gnet_pbc_diffs_mean = df_m3gnet.m3gnet_pbc_diffs.mean()
print(f"{m3gnet_pbc_diffs_mean = :.3}")

m3gnet_to_final_wbm_pbc_diffs_mean = df_m3gnet.m3gnet_to_final_wbm_pbc_diffs.mean()
print(f"{m3gnet_to_final_wbm_pbc_diffs_mean = :.3}")

print(f"{wbm_pbc_diffs_mean / m3gnet_pbc_diffs_mean = :.3}")
