# Trainable anomaly models (cardboard, top view, host Sticker, GPU RTX 4070 Ti)

Same data/crops as exp_backbone_eval.py. Good picks scored leave-one-run-out (single-run groups: 5 pick-folds instead of leave-one-pick-out); defects scored by a model trained on all good picks of the group. Whole-pick threshold = max held-out good score x margin. Per-group FR = good pick >= max good score of the OTHER runs x margin.

Baseline ResNet-18 PatchCore (exp/backbone_top): margin 1.0 TP 12 FR 7; 1.03 TP 10 FR 0; 1.15 TP 2 FR 0 (of 28 defects, 153 good). 14.8 ms/crop CPU.

## efficientad (13.3 ms/crop GPU, 464.9 ms/crop CPU torch; train per fold median 63s, max 65s)

info: `{"model_size": "small", "steps": 1000, "batch": 1, "penalty": "imagenette2-160 (C:/Users/aayus/AppData/Local/Temp/claude/6a649a77f82c3b65/31f4053a-ff24-4e4b-b972-2a059e17ff02/scratchpad/imagenette/imagenette2-160/train)", "quantiles_from": "training good crops (no separate validation split)"}`

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen, 5 folds) | tape 4 | 1.000 | 1 | 0 | 1 | 0 | 1 | 0 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | marker 6, tape 6 | 1.000 | 1 | 0 | 1 | 0 | 1 | 0 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 10 | 0 | 10 | 0 | 10 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 1 | 0 | 1 | 0 | 1 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | tape 6, other 6 | 0.790 | 37 | other 6 | 37 | tape 1,other 6 | 37 | tape 1,other 6 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen, 5 folds) | 0 | n/a | 1 | 0 | 1 | 0 | 1 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 5 | 0 | 5 | 0 | 5 | 0 |

Whole pick, anomaly only:

- margin 1.0: {'TP': 22, 'TN': 146, 'FR': 7, 'FN': 6}
- margin 1.03: {'TP': 21, 'TN': 153, 'FN': 7}
- margin 1.15: {'TP': 21, 'TN': 153, 'FN': 7}

## padim (19.2 ms/crop GPU, 71.7 ms/crop CPU torch; train per fold median 1s, max 24s)

info: `{"backbone": "resnet18", "layers": ["layer1", "layer2", "layer3"], "n_features": 100}`

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen, 5 folds) | tape 4 | 0.952 | 1 | tape 4 | 1 | tape 4 | 1 | tape 4 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | marker 6, tape 6 | 0.303 | 3 | tape 6,marker 6 | 2 | tape 6,marker 6 | 1 | tape 6,marker 6 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 0 | 0 | 0 | 0 | 0 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 2 | 0 | 2 | 0 | 1 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | other 6, tape 6 | 0.248 | 37 | tape 4,other 6 | 37 | tape 4,other 6 | 37 | tape 4,other 6 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen, 5 folds) | 0 | n/a | 2 | 0 | 1 | 0 | 0 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 5 | 0 | 5 | 0 | 3 | 0 |

Whole pick, anomaly only:

- margin 1.0: {'FN': 26, 'TN': 146, 'FR': 7, 'TP': 2}
- margin 1.03: {'FN': 26, 'TN': 153, 'TP': 2}
- margin 1.15: {'FN': 26, 'TN': 153, 'TP': 2}

## simplenet (10.5 ms/crop GPU, 205.8 ms/crop CPU torch; train per fold median 100s, max 101s)

info: `{"model": "SuperSimpleNet (anomalib 2.7)", "backbone": "wide_resnet50_2.tv_in1k", "layers": ["layer2", "layer3"], "steps": 300, "batch": 8, "perlin_threshold": 0.2}`

| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |
|---|---|---|---|---|---|---|---|---|---|
| button_ss_long|lying|top|cardboard | 21 (1) (same specimen, 5 folds) | tape 4 | 0.881 | 1 | tape 4 | 1 | tape 4 | 1 | tape 4 |
| hex_bolt_partial|lying|top|cardboard | 33 (3) | marker 6, tape 6 | 0.215 | 1 | tape 6,marker 6 | 1 | tape 6,marker 6 | 1 | tape 6,marker 6 |
| hex_bolt_short|lying|top|cardboard | 11 (2) | 0 | n/a | 1 | 0 | 1 | 0 | 1 | 0 |
| hex_nut|lying|top|cardboard | 21 (5) | 0 | n/a | 14 | 0 | 14 | 0 | 13 | 0 |
| socket_m16|lying|top|cardboard | 40 (2) | other 6, tape 6 | 0.869 | 10 | tape 4,other 6 | 5 | tape 4,other 6 | 0 | tape 5,other 6 |
| socket_thin_long|lying|top|cardboard | 20 (1) (same specimen, 5 folds) | 0 | n/a | 3 | 0 | 3 | 0 | 2 | 0 |
| socket_thin_short|lying|top|cardboard | 7 (3) | 0 | n/a | 1 | 0 | 1 | 0 | 1 | 0 |

Whole pick, anomaly only:

- margin 1.0: {'FN': 26, 'TN': 146, 'FR': 7, 'TP': 2}
- margin 1.03: {'FN': 26, 'TN': 153, 'TP': 2}
- margin 1.15: {'FN': 27, 'TN': 153, 'TP': 1}
