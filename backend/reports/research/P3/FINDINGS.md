# P3 Findings

## Supported

- Dataset rows now carry `episode_id`, `scenario_type`, JSON `scenario_params`, `onset_tick`, `end_tick`, `attack_active`, `evidence_visible`, and JSON `affected_rtus`; legacy labels remain present.
- The generator supports `stress`, `operational`, and `clean` prevalence regimes; `--compressed-stress` explicitly selects the legacy 900-second simulated tick, while the default simulated tick is one second.
- Load variation is reproducibly seeded and includes per-bus phase/shape offsets, OU variability, day scaling, and occasional persistent load steps. `ood` selects a distinct profile family and noise scale.
- Descriptor smoke output: `{"splits": [{"attack_active_rows": 0, "class_counts": {"Normal": 96, "Sensor Malfunction": 4}, "class_shares": {"Normal": 0.96, "Sensor Malfunction": 0.04}, "columns": ["nbd_unexpected_write_count", "nbd_mean_response_time_ms", "nbd_std_response_time_ms", "nbd_distinct_sources_count", "nbd_fc3_read_count", "nbd_fc6_write_count", "nbd_fc16_write_count", "nbd_error_count", "nbd_traffic_volume", "nbd_modbus_anomaly_rate", "pcd_max_lnr", "pcd_is_target_rtu_max_lnr", "pcd_chi2_statistic", "pcd_chi2_ratio", "pcd_chi2_failed", "pcd_target_rtu_v_residual", "pcd_target_rtu_p_residual", "pcd_target_rtu_is_flagged", "pcd_global_bad_data_flag", "pcd_voltage_pu_reported", "pcd_voltage_dev_nominal", "pcd_p_mw_reported", "pcd_status_code", "pcd_physics_network_disagreement_index", "pcd_temporal_dv_dt_3tick", "pcd_temporal_dp_dt_3tick", "pcd_temporal_dq_dt_3tick", "pcd_cross_rtu_voltage_divergence", "pcd_resid_jump", "pcd_resid_persist", "pcd_resid_concentration", "pcd_resid_rtu_share", "pcd_resid_breadth_count", "pcd_resid_breadth_frac", "dpn_legacy", "dpn_ing_delta", "dpn_ing_resid", "tick", "rtu_id", "top_level_label", "subtype_label", "episode_id", "scenario_type", "scenario_params", "onset_tick", "end_tick", "attack_active", "evidence_visible", "affected_rtus"], "episode_counts_by_type": {"Normal": 1, "Sensor Malfunction": 1}, "evidence_visible_fraction_by_scenario": {"Normal": 0.0, "Sensor Malfunction": 0.2}, "missing_counts": {}, "rows": 100, "split": "smoke", "subtype_counts": {"normal": 96, "sensor_drift": 4}, "time_shares_by_scenario": {"Normal": 0.8, "Sensor Malfunction": 0.2}}], "task_id": "P3"}`.

## Not supported

- No candidate model was trained, tuned, selected, or evaluated in P3.
- The smoke run is not evidence of prevalence or generalization; it is only an end-to-end schema and runtime check.
- The current simulation has no separate benign-event injector, so the operational regime represents the documented 5% benign-event intent through the existing Normal class rather than claiming a distinct benign-event label.

## Unresolved

- Full seed-band generation has not been run in this task; the bands are recorded in generator manifests for later controlled generation.
- Command-injection evidence visibility is tied to the observer-verified write appearing in the rolling traffic window; physical consequence evidence is not synthesized.

## Test result

- Backend suite summary: `1 failed, 357 passed, 523 warnings`; the known citation-lint baseline failure, if present, is not changed by P3.
