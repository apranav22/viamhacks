# Backbone comparison (cardboard, aggregate=top1, host Sticker)

Leave-one-run-out good scores; thresholds from good only. FR = good rejected, FN = defect passed.

## resnet18_patchcore (320 px, 14.8 ms/crop torch cpu)

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen) | tape 4 | 0.976 | 1 | tape 2 | 1 | tape 3 | 1 | tape 4 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | tape 6, marker 6 | 0.949 | 1 | tape 6,marker 6 | 1 | tape 6,marker 6 | 0 | tape 6,marker 6 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 10 | 0 | 10 | 0 | 10 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 1 | 0 | 0 | 0 | 0 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | tape 6, other 6 | 0.948 | 35 | tape 2 | 34 | tape 3 | 27 | tape 5,other 5 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen) | 0 | n/a | 1 | 0 | 1 | 0 | 0 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 5 | 0 | 5 | 0 | 3 | 0 |

Whole pick, anomaly only (any view over threshold rejects):

- margin 1.0: {'TP': 12, 'FN': 16, 'TN': 146, 'FR': 7}
- margin 1.03: {'FN': 18, 'TP': 10, 'TN': 153}
- margin 1.15: {'FN': 26, 'TN': 153, 'TP': 2}

development-v1 members with a top crop here: 62
- margin 1.0: {'TP': 12, 'FN': 16, 'FR': 1, 'TN': 33}
- margin 1.03: {'TP': 10, 'FN': 18, 'FR': 0, 'TN': 34}
- margin 1.15: {'TP': 2, 'FN': 26, 'FR': 0, 'TN': 34}

Known-defect probe: `{"top": {"tape_caught": "2/16", "good_flagged": "18/153", "tape_not_measurable": 0, "tape_probe_flags_marker": "4/6", "tape_probe_flags_other": "1/6"}}`

## dinov2_s (448 px, 88.8 ms/crop torch cpu)

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen) | tape 4 | 0.964 | 1 | tape 3 | 1 | tape 4 | 1 | tape 4 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | tape 6, marker 6 | 0.977 | 1 | tape 4,marker 5 | 1 | tape 5,marker 6 | 1 | tape 6,marker 6 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 10 | 0 | 10 | 0 | 10 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 3 | 0 | 3 | 0 | 3 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | tape 6, other 6 | 0.948 | 37 | tape 4,other 6 | 37 | tape 4,other 6 | 35 | tape 5,other 6 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen) | 0 | n/a | 1 | 0 | 1 | 0 | 1 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 5 | 0 | 5 | 0 | 5 | 0 |

Whole pick, anomaly only (any view over threshold rejects):

- margin 1.0: {'TP': 6, 'FN': 22, 'TN': 146, 'FR': 7}
- margin 1.03: {'FN': 25, 'TN': 153, 'TP': 3}
- margin 1.15: {'FN': 27, 'TN': 153, 'TP': 1}

development-v1 members with a top crop here: 62
- margin 1.0: {'TP': 6, 'FN': 22, 'FR': 2, 'TN': 32}
- margin 1.03: {'TP': 3, 'FN': 25, 'FR': 0, 'TN': 34}
- margin 1.15: {'TP': 1, 'FN': 27, 'FR': 0, 'TN': 34}

Known-defect probe: `{"top": {"tape_caught": "8/16", "good_flagged": "12/153", "tape_not_measurable": 0, "tape_probe_flags_marker": "5/6", "tape_probe_flags_other": "2/6"}}`
