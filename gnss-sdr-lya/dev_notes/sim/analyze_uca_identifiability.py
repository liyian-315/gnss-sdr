#!/usr/bin/env python3
"""Pre-hardware array identifiability and manifold-error budget analysis.

All generated results are [ideal simulation]. If measured Phase A reference
CSVs are supplied, temporal/joint A0 rows are [texture synthesis]. Nothing in
this tool is evidence about Y790s hardware.
"""

import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_space_delay_twosource as sd  # noqa: E402
import fit_two_path as ftp  # noqa: E402


L5_WAVELENGTH_M = 0.2548
UCA8_REFERENCE_RADIUS_M = 0.162
TYPICAL_DELTAS_DEG = (0, 5, 10, 20, 30, 40, 60, 90)
PHASE_RMS_DEG = (0, 1, 2, 5, 10, 15, 20, 30)
DRIFT_RMS_DEG = (0, 1, 2, 5, 10, 20)
MANIFOLD_ERROR_PERCENT = (1, 3, 5, 8, 10, 15)


def uca_xyz(n_elements=8, radius_m=UCA8_REFERENCE_RADIUS_M):
    phi = 2.0 * np.pi * np.arange(n_elements) / n_elements
    return np.column_stack([radius_m * np.cos(phi), radius_m * np.sin(phi),
                            np.zeros(n_elements)])


def spatial_metrics(array_xyz_m, wavelength_m, az0_deg, delta_az_deg):
    a0 = sd.steering_xyz(array_xyz_m, wavelength_m, az0_deg)
    a1 = sd.steering_xyz(array_xyz_m, wavelength_m, az0_deg + delta_az_deg)
    design = np.column_stack([a0 / np.linalg.norm(a0), a1 / np.linalg.norm(a1)])
    singular = np.linalg.svd(design, compute_uv=False)
    return {
        "mu_spatial": sd.coherence(a0, a1),
        "condition_number": float(np.inf if singular[-1] < 1e-14
                                  else singular[0] / singular[-1]),
        "smallest_singular_value": float(singular[-1]),
    }


def temporal_coherence(kernel_csv, delta_tau_chips, taps=None):
    try:
        ktaps, kernel = ftp.load_reference_csv(kernel_csv)
    except ValueError as error:
        # Some Windows exports add a UTF-8 BOM to the first Phase A column.
        data = np.genfromtxt(kernel_csv, delimiter=",", names=True,
                             dtype=None, encoding="utf-8-sig")
        if not data.dtype.names or "tap_chips" not in data.dtype.names:
            raise error
        ktaps = np.atleast_1d(data["tap_chips"]).astype(float)
        kernel = (np.atleast_1d(data["coherent_re"]).astype(float) +
                  1j * np.atleast_1d(data["coherent_im"]).astype(float))
    if taps is None:
        taps = ktaps
    r0 = sd.kernel_vec(0.0, taps, ktaps, kernel)
    r1 = sd.kernel_vec(delta_tau_chips, taps, ktaps, kernel)
    return sd.coherence(r0, r1)


def joint_metrics(mu_spatial, mu_temporal):
    mu = float(np.clip(mu_spatial * mu_temporal, 0.0, 1.0))
    singular = np.sqrt(np.maximum([1.0 + mu, 1.0 - mu], 0.0))
    return {
        "mu_joint": mu,
        "condition_number": float(np.inf if singular[1] < 1e-14
                                  else singular[0] / singular[1]),
        "smallest_singular_value": float(singular[1]),
    }


def scan_spatial(array_xyz_m, wavelength_m):
    rows = []
    for az0 in np.arange(0.0, 360.0, 5.0):
        for delta in np.arange(0.0, 181.0, 1.0):
            row = spatial_metrics(array_xyz_m, wavelength_m, az0, delta)
            row.update(absolute_az_deg=float(az0), delta_az_deg=float(delta))
            rows.append(row)
    return rows


def summarize_spatial(rows):
    summary = []
    for delta in range(181):
        selected = [r for r in rows if r["delta_az_deg"] == delta]
        item = {"delta_az_deg": delta}
        for key in ("mu_spatial", "condition_number", "smallest_singular_value"):
            values = np.array([r[key] for r in selected], dtype=np.float64)
            item.update({key + "_min": float(np.min(values)),
                         key + "_median": float(np.median(values)),
                         key + "_max": float(np.max(values))})
        summary.append(item)
    return summary


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_spatial(output_dir, rows, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matrix = np.array([r["mu_spatial"] for r in rows]).reshape(72, 181)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    image = ax.imshow(matrix, origin="lower", aspect="auto", extent=[0, 180, 0, 355],
                      vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set(xlabel="delta az (deg)", ylabel="absolute az0 (deg)",
           title="[ideal simulation] 8-UCA spatial coherence")
    fig.colorbar(image, ax=ax, label="mu_spatial")
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "uca8_mu_spatial_map.png"), dpi=160)
    plt.close(fig)

    delta = np.array([r["delta_az_deg"] for r in summary])
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, key, label in zip(axes,
                              ("mu_spatial", "condition_number", "smallest_singular_value"),
                              ("mu_spatial", "condition number", "smallest singular value")):
        for stat in ("min", "median", "max"):
            ax.plot(delta, [r[key + "_" + stat] for r in summary], label=stat)
        ax.set(xlabel="delta az (deg)", ylabel=label)
        ax.grid(True, alpha=0.3)
    axes[1].set_ylim(1, 20)
    axes[1].legend()
    fig.suptitle("[ideal simulation] absolute-bearing envelope")
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "uca8_spatial_envelopes.png"), dpi=160)
    plt.close(fig)


def plot_joint(output_dir, kernel_label, joint_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tau_values = sorted(set(r["delta_tau_chips"] for r in joint_rows))
    az_values = sorted(set(r["delta_az_deg"] for r in joint_rows))
    safe_label = os.path.splitext(os.path.basename(kernel_label))[0]
    for key, title in (("mu_joint", "joint coherence"),
                       ("condition_number", "condition number"),
                       ("smallest_singular_value", "smallest singular value")):
        matrix = np.array([[next(r[key] for r in joint_rows
                                 if r["delta_tau_chips"] == tau and
                                 r["delta_az_deg"] == az)
                            for az in az_values] for tau in tau_values])
        fig, ax = plt.subplots(figsize=(8, 4.5))
        image = ax.imshow(matrix, origin="lower", aspect="auto",
                          extent=[min(az_values), max(az_values),
                                  min(tau_values), max(tau_values)], cmap="viridis")
        for marker in (0.0, 0.5, 1.0):
            ax.axhline(marker, color="white", lw=0.7, ls="--")
        ax.set(xlabel="delta az (deg)", ylabel="delta tau (chip)",
               title="[texture synthesis] %s" % title)
        fig.colorbar(image, ax=ax, label=key)
        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, "%s_%s.png" % (safe_label, key)), dpi=160)
        plt.close(fig)

def fixed_phase_gain(n_elements, rms_deg, rng):
    phase = np.zeros(n_elements)
    if n_elements > 1 and rms_deg > 0:
        draw = rng.standard_normal(n_elements - 1)
        draw *= rms_deg / np.sqrt(np.mean(draw ** 2))
        phase[1:] = draw
    return np.exp(1j * np.radians(phase))


def slow_drift_gain(n_blocks, n_elements, run_rms_deg, rng):
    gain = np.ones((n_blocks, n_elements), dtype=np.complex128)
    for channel in range(1, n_elements):
        walk = np.cumsum(rng.standard_normal(n_blocks))
        walk -= walk.mean()
        if np.std(walk) > 0 and run_rms_deg > 0:
            walk *= run_rms_deg / np.std(walk)
        gain[:, channel] = np.exp(1j * np.radians(walk))
    return gain


def manifold_gain(n_elements, rms_percent, rng):
    amplitude = np.ones(n_elements)
    phase = np.zeros(n_elements)
    if n_elements > 1 and rms_percent > 0:
        amp_draw = rng.standard_normal(n_elements - 1)
        amp_draw *= (rms_percent / 100.0) / np.sqrt(np.mean(amp_draw ** 2))
        phase_draw = rng.standard_normal(n_elements - 1)
        # A p-percent complex error uses p/100 RMS amplitude error and p/100
        # radians RMS phase error, so the two components share one scale.
        phase_draw *= np.degrees(rms_percent / 100.0) / np.sqrt(np.mean(phase_draw ** 2))
        amplitude[1:] += amp_draw
        phase[1:] = phase_draw
    return amplitude * np.exp(1j * np.radians(phase))


def run_one_a1(array_xyz_m, wavelength_m, kernel, taps, truth_gain, seed,
               single_source=False):
    rng = np.random.default_rng(seed)
    truth = dict(az0=17.0, az1=47.0, tau0=0.07, tau1=0.57, ratio_db=-6.0)
    dense = sd.synth_dense(
        taps, taps, kernel, len(array_xyz_m), 0.5, truth["az0"], truth["az1"],
        truth["tau0"], truth["tau1"], truth["ratio_db"], 12, 0.03, rng,
        single_source=single_source, array_xyz_m=array_xyz_m,
        wavelength_m=wavelength_m, truth_gain=truth_gain)
    result = sd.fit(
        dense, taps, taps, kernel, len(array_xyz_m), 0.5, 29.3,
        angle_grid=np.arange(0.0, 81.0, 10.0),
        tau0_grid=np.arange(-0.1, 0.21, 0.1),
        tau1_grid=np.arange(0.3, 0.81, 0.1), array_xyz_m=array_xyz_m,
        wavelength_m=wavelength_m)
    result.update(delay_error_chips=(result["delta_chips"] - 0.5),
                  amplitude_ratio_error_db=(result["amp_ratio_db"] - truth["ratio_db"]),
                  single_source=single_source)
    return result


def sensitivity_rows(seed, realizations):
    # The built-in kernel is used only for [ideal simulation] mismatch sensitivity.
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    array_xyz_m = uca_xyz()
    rows = []
    cases = []
    for value in PHASE_RMS_DEG:
        cases.append(("fixed_phase_bias", value, "deg_rms"))
    for value in DRIFT_RMS_DEG:
        cases.append(("slow_random_walk", value, "deg_rms_over_run"))
    for value in MANIFOLD_ERROR_PERCENT:
        cases.append(("amplitude_plus_phase_manifold", value, "percent_complex_rms"))
    for kind, level, unit in cases:
        trial_rows = []
        for realization in range(realizations):
            kind_offset = {"fixed_phase_bias": 10000, "slow_random_walk": 20000,
                           "amplitude_plus_phase_manifold": 30000}[kind]
            # Common random numbers: each model reuses one perturbation direction
            # and one scene/noise realization across levels; only error scale changes.
            rng = np.random.default_rng(seed + kind_offset + realization)
            if kind == "fixed_phase_bias":
                gain = fixed_phase_gain(8, level, rng)
            elif kind == "slow_random_walk":
                gain = slow_drift_gain(12, 8, level, rng)
            else:
                gain = manifold_gain(8, level, rng)
            result = run_one_a1(array_xyz_m, L5_WAVELENGTH_M, kernel, taps, gain,
                                seed + realization)
            trial_rows.append(result)
            control = run_one_a1(array_xyz_m, L5_WAVELENGTH_M, kernel, taps, gain,
                                 seed + realization,
                                 single_source=True)
            result["single_source_false_positive"] = control["state"] != "NO_SECOND_SOURCE"
        row = {"evidence": "ideal_simulation", "error_model": kind,
               "error_level": level, "error_unit": unit,
               "realizations": realizations, "seed": seed,
               "threshold_status": "PROVISIONAL"}
        for key in ("improvement_db", "delay_error_chips", "amplitude_ratio_error_db",
                    "mu_joint", "cond"):
            values = np.array([r[key] for r in trial_rows])
            row[key + "_median"] = float(np.median(values))
            row[key + "_p90_abs"] = float(np.percentile(np.abs(values), 90))
        row["reliable_fraction"] = float(np.mean([r["state"] == "RELIABLE"
                                                  for r in trial_rows]))
        row["single_source_false_positive_fraction"] = float(np.mean(
            [r["single_source_false_positive"] for r in trial_rows]))
        row["decision_counts"] = json.dumps(
            {state: sum(r["state"] == state for r in trial_rows)
             for state in ("RELIABLE", "MARGINAL", "UNRESOLVED", "NO_SECOND_SOURCE")},
            sort_keys=True)
        rows.append(row)
    return rows


def self_test():
    legacy = sd.steering(30.0, 4, 0.5)
    xyz_legacy = sd.steering_xyz(sd.ula_xyz(4, 0.5), 1.0, 30.0)
    assert np.allclose(legacy, xyz_legacy)

    uca = uca_xyz()
    for az0 in (0.0, 17.0, 91.0):
        assert spatial_metrics(uca, L5_WAVELENGTH_M, az0, 0.0)["mu_spatial"] > 1 - 1e-12
        assert np.isinf(spatial_metrics(uca, L5_WAVELENGTH_M, az0, 0.0)["condition_number"])
    rotated = [spatial_metrics(uca, L5_WAVELENGTH_M, az, 30.0)["mu_spatial"]
               for az in np.arange(0.0, 360.0, 45.0)]
    assert np.ptp(rotated) < 1e-12
    assert spatial_metrics(uca, L5_WAVELENGTH_M, 13.0, 60.0)["condition_number"] < \
        spatial_metrics(uca, L5_WAVELENGTH_M, 13.0, 5.0)["condition_number"]

    rng1 = np.random.default_rng(99)
    rng2 = np.random.default_rng(99)
    gain1 = fixed_phase_gain(8, 10, rng1)
    gain2 = fixed_phase_gain(8, 10, rng2)
    assert np.array_equal(gain1, gain2)
    model_before = sd.steering_xyz(uca, L5_WAVELENGTH_M, 17.0)
    assert not np.allclose(model_before * gain1, model_before)
    assert np.array_equal(model_before, sd.steering_xyz(uca, L5_WAVELENGTH_M, 17.0))
    assert np.array_equal(fixed_phase_gain(8, 0, rng1), np.ones(8))
    taps = np.round(np.arange(-1.5, 1.5001, 0.1), 4)
    kernel = ftp.synth_kernel(taps)
    baseline = run_one_a1(uca, L5_WAVELENGTH_M, kernel, taps, None, 123)
    zero_error = run_one_a1(uca, L5_WAVELENGTH_M, kernel, taps, np.ones(8), 123)
    for key in ("improvement_db", "delta_chips", "amp_ratio_db", "mu_joint", "cond"):
        assert baseline[key] == zero_error[key]
    print("self-test: PASS (ULA regression, UCA symmetry/degeneracy/conditioning, "
          "truth-model independence, zero-error baseline, fixed-seed reproducibility)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    parser.add_argument("--kernel", action="append", default=[],
                        help="TRUSTWORTHY Phase A reference CSV; repeat for multiple references")
    parser.add_argument("--run-sensitivity", action="store_true")
    parser.add_argument("--realizations", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7908)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output_dir:
        parser.error("--output-dir is required unless --self-test is used")
    os.makedirs(args.output_dir, exist_ok=True)

    uca = uca_xyz()
    rows = scan_spatial(uca, L5_WAVELENGTH_M)
    summary = summarize_spatial(rows)
    write_csv(os.path.join(args.output_dir, "uca8_spatial_summary.csv"), summary)
    plot_spatial(args.output_dir, rows, summary)

    typical = []
    for delta in TYPICAL_DELTAS_DEG:
        selected = [r for r in rows if r["delta_az_deg"] == delta]
        item = {"evidence": "ideal_simulation", "delta_az_deg": delta}
        for key in ("mu_spatial", "condition_number", "smallest_singular_value"):
            values = np.array([r[key] for r in selected])
            item.update({key + "_min": float(np.min(values)),
                         key + "_median": float(np.median(values)),
                         key + "_max": float(np.max(values))})
        typical.append(item)
    write_csv(os.path.join(args.output_dir, "uca8_spatial_typical.csv"), typical)

    ula = sd.ula_xyz(4, 0.5, L5_WAVELENGTH_M)
    ula_rows = scan_spatial(ula, L5_WAVELENGTH_M)
    ula_typical = []
    for delta in TYPICAL_DELTAS_DEG:
        selected = [r for r in ula_rows if r["delta_az_deg"] == delta]
        item = {"evidence": "ideal_simulation", "array": "4-ULA-lambda-over-2",
                "delta_az_deg": delta}
        for key in ("mu_spatial", "condition_number", "smallest_singular_value"):
            values = np.array([r[key] for r in selected])
            item.update({key + "_min": float(np.min(values)),
                         key + "_median": float(np.median(values)),
                         key + "_max": float(np.max(values))})
        ula_typical.append(item)
    special = spatial_metrics(ula, L5_WAVELENGTH_M, 0.0, 30.0)
    write_csv(os.path.join(args.output_dir, "ula4_spatial_typical.csv"), ula_typical)
    with open(os.path.join(args.output_dir, "ula4_0deg_30deg_special.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"evidence": "ideal_simulation", "absolute_az_deg": 0,
                   "delta_az_deg": 30, **special,
                   "warning": "special orthogonal geometry; not an 8-UCA expectation"},
                  fh, indent=2)
        fh.write("\n")

    temporal = []
    for kernel_path in args.kernel:
        kernel_joint = []
        for delta_tau in (0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
            mu_t = temporal_coherence(kernel_path, delta_tau)
            temporal.append({"evidence": "texture_synthesis", "kernel": os.path.abspath(kernel_path),
                             "delta_tau_chips": delta_tau,
                             "mu_temporal": mu_t})
        for delta_tau in np.arange(0.0, 1.001, 0.05):
            mu_t = temporal_coherence(kernel_path, float(delta_tau))
            for delta_az in range(181):
                mu_s = next(r["mu_spatial_median"] for r in summary
                            if r["delta_az_deg"] == delta_az)
                item = joint_metrics(mu_s, mu_t)
                item.update(evidence="texture_synthesis", kernel=os.path.abspath(kernel_path),
                            delta_tau_chips=float(delta_tau), delta_az_deg=delta_az,
                            mu_spatial=mu_s, mu_temporal=mu_t)
                kernel_joint.append(item)
        write_csv(os.path.join(args.output_dir,
                               os.path.splitext(os.path.basename(kernel_path))[0] + "_joint.csv"),
                  kernel_joint)
        plot_joint(args.output_dir, kernel_path, kernel_joint)
    if temporal:
        write_csv(os.path.join(args.output_dir, "measured_kernel_temporal.csv"), temporal)

    if args.run_sensitivity:
        if args.realizations < 2:
            parser.error("--realizations must be at least 2")
        write_csv(os.path.join(args.output_dir, "uca8_phase_manifold_sensitivity.csv"),
                  sensitivity_rows(args.seed, args.realizations))

    metadata = {"evidence": "ideal_simulation", "seed": args.seed,
                "uca_reference": {"n_elements": 8, "radius_m": UCA8_REFERENCE_RADIUS_M,
                                  "wavelength_m": L5_WAVELENGTH_M,
                                  "note": "theoretical reference, not actual hardware geometry"},
                "absolute_az_deg": "0:5:355", "delta_az_deg": "0:1:180",
                "kernel_references": [os.path.abspath(p) for p in args.kernel],
                "measured_texture_status": ("provided" if args.kernel
                                            else "NOT_RUN_MISSING_INPUT"),
                "thresholds": "PROVISIONAL",
                "reproduce": "python dev_notes/sim/analyze_uca_identifiability.py "
                             "--output-dir <dir> [--kernel <PhaseA.csv> ...] "
                             "[--run-sensitivity] --seed %d" % args.seed}
    with open(os.path.join(args.output_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
        fh.write("\n")
    print("wrote analysis to %s" % args.output_dir)
    if not args.kernel:
        print("measured kernel/texture layer: NOT_RUN_MISSING_INPUT")


if __name__ == "__main__":
    main()
