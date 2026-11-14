# Backbone comparison (cardboard, aggregate=top1, host Sticker)

Leave-one-run-out good scores; thresholds from good only. FR = good rejected, FN = defect passed.

## dinov3_s (448 px, 311.4 ms/crop torch cpu)

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen) | tape 4 | 0.952 | 1 | tape 4 | 1 | tape 4 | 1 | tape 4 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | tape 6, marker 6 | 0.970 | 1 | tape 6,marker 6 | 1 | tape 6,marker 6 | 1 | tape 6,marker 6 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 10 | 0 | 10 | 0 | 10 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 3 | 0 | 3 | 0 | 3 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | tape 6, other 6 | 0.998 | 26 | tape 1 | 20 | tape 2 | 13 | tape 3 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen) | 0 | n/a | 1 | 0 | 1 | 0 | 0 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 4 | 0 | 2 | 0 | 1 | 0 |

Whole pick, anomaly only (any view over threshold rejects):

- margin 1.0: {'FN': 17, 'TN': 146, 'FR': 7, 'TP': 11}
- margin 1.03: {'FN': 18, 'TN': 153, 'TP': 10}
- margin 1.15: {'FN': 19, 'TN': 153, 'TP': 9}

development-v1 members with a top crop here: 62
- margin 1.0: {'TP': 11, 'FN': 17, 'FR': 2, 'TN': 32}
- margin 1.03: {'TP': 10, 'FN': 18, 'FR': 0, 'TN': 34}
- margin 1.15: {'TP': 9, 'FN': 19, 'FR': 0, 'TN': 34}

Known-defect probe: `{"top": {"tape_caught": "6/16", "good_flagged": "7/153", "tape_not_measurable": 0, "tape_probe_flags_marker": "6/6", "tape_probe_flags_other": "1/6"}}`
