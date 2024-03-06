"""Concatenate MACE results from multiple data files generated by slurm job array
into single file.
"""

# %%
from __future__ import annotations

import os
from glob import glob

import pandas as pd
from pymatgen.core import Structure
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatviz import density_scatter
from tqdm import tqdm

from matbench_discovery.data import DATA_FILES, as_dict_handler, df_wbm
from matbench_discovery.energy import get_e_form_per_atom
from matbench_discovery.enums import Key, Task

__author__ = "Janosh Riebesell"
__date__ = "2023-03-01"


# %%
module_dir = os.path.dirname(__file__)
task_type = Task.IS2RE
e_form_mace_col = "e_form_per_atom_mace"
date = "2023-12-11"
glob_pattern = f"{date}-mace-wbm-{task_type}*/*.json.gz"
file_paths = sorted(glob(f"{module_dir}/{glob_pattern}"))
print(f"Found {len(file_paths):,} files for {glob_pattern = }")
struct_col = "mace_structure"

dfs: dict[str, pd.DataFrame] = {}


# %%
for file_path in tqdm(file_paths):
    if file_path in dfs:
        continue
    df = pd.read_json(file_path).set_index(Key.mat_id)
    # drop trajectory to save memory
    dfs[file_path] = df.drop(columns="mace_trajectory", errors="ignore")

df_mace = pd.concat(dfs.values()).round(4)


# %%
df_cse = pd.read_json(DATA_FILES.wbm_computed_structure_entries).set_index(Key.mat_id)

df_cse[Key.cse] = [
    ComputedStructureEntry.from_dict(dct) for dct in tqdm(df_cse[Key.cse])
]


# %% transfer mace energies and relaxed structures WBM CSEs since MP2020 energy
# corrections applied below are structure-dependent (for oxides and sulfides)
cse: ComputedStructureEntry
for row in tqdm(df_mace.itertuples(), total=len(df_mace), desc="ML energies to CSEs"):
    mat_id, struct_dict, mace_energy, *_ = row
    mlip_struct = Structure.from_dict(struct_dict)
    df_mace.at[mat_id, struct_col] = mlip_struct  # noqa: PD008
    cse = df_cse.loc[mat_id, Key.cse]
    cse._energy = mace_energy  # cse._energy is the uncorrected energy  # noqa: SLF001
    cse._structure = mlip_struct  # noqa: SLF001
    df_mace.loc[mat_id, Key.cse] = cse


# %% apply energy corrections
processed = MaterialsProject2020Compatibility().process_entries(
    df_mace[Key.cse], verbose=True, clean=True
)
assert len(processed) == len(df_mace)


# %% compute corrected formation energies
df_mace[Key.formula] = df_wbm[Key.formula]
df_mace[e_form_mace_col] = [
    get_e_form_per_atom(dict(energy=cse.energy, composition=formula))
    for formula, cse in tqdm(
        df_mace.set_index(Key.formula)[Key.cse].items(), total=len(df_mace)
    )
]
df_wbm[e_form_mace_col] = df_mace[e_form_mace_col]


# %%
bad_mask = (df_wbm[e_form_mace_col] - df_wbm[Key.e_form]) < -5
print(f"{sum(bad_mask)=}")
ax = density_scatter(df=df_wbm[~bad_mask], x=Key.e_form, y=e_form_mace_col)


# %%
out_path = file_paths[0].rsplit("/", 1)[0]
df_mace = df_mace.round(4)
df_mace.select_dtypes("number").to_csv(f"{out_path}.csv.gz")
df_mace[~bad_mask].select_dtypes("number").to_csv(f"{out_path}-no-bad.csv.gz")
df_mace.reset_index().to_json(f"{out_path}.json.gz", default_handler=as_dict_handler)

df_bad = df_mace[bad_mask].drop(columns=[Key.cse, struct_col])
df_bad[Key.e_form] = df_wbm[Key.e_form]
df_bad.to_csv(f"{out_path}-bad.csv")

# in_path = f"{module_dir}/2023-12-11-mace-wbm-IS2RE-FIRE"
# df_mace = pd.read_csv(f"{in_path}.csv.gz").set_index(Key.mat_id)
# df_mace = pd.read_json(f"{in_path}.json.gz").set_index(Key.mat_id)
