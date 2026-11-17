"""Backends for exp_trainable_eval.py: fit(list of PIL crops) -> model; score(model, crops) -> list of float.

anomalib 2.7 torch model classes driven directly (no Engine): EfficientAD-S (student/AE trained on the good crops with
the ImageNette penalty; map quantiles from the training good crops), PaDiM (ResNet-18, Gaussian per position),
SuperSimpleNet (WideResNet-50 features, synthetic Perlin feature anomalies, unsupervised).
"""
import os
import random
import time

import numpy as np
import torch

IMNET = os.environ.get("IMAGENETTE_DIR", "")
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def to_tensor(imgs, size):
    arr = [np.asarray(im.convert("RGB").resize((size, size)), np.float32) / 255 for im in imgs]
    return torch.from_numpy(np.stack(arr)).permute(0, 3, 1, 2).contiguous()


class Base:
    norm = False

    def __init__(self, device, size):
        self.device, self.size = torch.device(device), size

    def prep(self, imgs):
        x = to_tensor(imgs, self.size)
        return (x - MEAN) / STD if self.norm else x

    @torch.no_grad()
    def infer(self, model, x):
        return model(x).pred_score.reshape(-1)

    @torch.no_grad()
    def score(self, model, imgs):
        model.eval()
        x = self.prep(imgs)
        out = []
        for i in range(0, len(x), 8):
            out += self.infer(model, x[i:i + 8].to(self.device)).float().cpu().tolist()
        return out

    def bench(self, imgs):
        model = self.fit(imgs[:16])
        res = {}
        x = self.prep(imgs[:1])
        for dev in ("cuda", "cpu"):
            m = model.to(dev).eval()
            xx = x.to(dev)
            with torch.no_grad():
                for _ in range(3):
                    self.infer(m, xx)
                if dev == "cuda":
                    torch.cuda.synchronize()
                t = time.perf_counter()
                n = 20 if dev == "cuda" else 5
                for _ in range(n):
                    self.infer(m, xx)
                if dev == "cuda":
                    torch.cuda.synchronize()
            res[f"{'gpu' if dev == 'cuda' else 'cpu'}_ms"] = (time.perf_counter() - t) * 1000 / n
        return res


class EfficientAD(Base):
    def __init__(self, device, steps=300, size=256):
        super().__init__(device, size)
        self.steps = steps
        if not IMNET or not os.path.isdir(IMNET):
            raise RuntimeError("set IMAGENETTE_DIR to an ImageNette folder (penalty images)")
        self.info = {"model_size": "small", "steps": steps, "batch": 1, "penalty": f"imagenette2-160 ({IMNET})",
                     "quantiles_from": "training good crops (no separate validation split)"}

    def fit(self, imgs):
        from anomalib.models import EfficientAd
        lm = EfficientAd(model_size="small", imagenet_dir=IMNET, pre_processor=False, post_processor=False,
                         evaluator=False, visualizer=False).to(self.device)
        lm.prepare_pretrained_model()
        lm.prepare_imagenette_data((self.size, self.size))
        m = lm.model
        x = self.prep(imgs).to(self.device)
        with torch.no_grad():
            y = torch.cat([m.teacher(x[i:i + 8]) for i in range(0, len(x), 8)])
            mean = y.mean(dim=(0, 2, 3))
            std = torch.sqrt((y ** 2).mean(dim=(0, 2, 3)) - mean ** 2)
            m.mean_std.update({"mean": mean[None, :, None, None].float(), "std": std[None, :, None, None].float()})
        opt = torch.optim.Adam(list(m.student.parameters()) + list(m.ae.parameters()), lr=1e-4, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=max(1, int(0.95 * self.steps)), gamma=0.1)
        m.train()
        it = iter(lm.imagenet_loader)
        for _ in range(self.steps):
            try:
                imn = next(it)[0].to(self.device)
            except StopIteration:
                it = iter(lm.imagenet_loader)
                imn = next(it)[0].to(self.device)
            i = random.randrange(len(x))
            l_st, l_ae, l_stae = m(batch=x[i:i + 1], batch_imagenet=imn)
            loss = l_st + l_ae + l_stae
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
        m.eval()
        with torch.no_grad():
            st, ae = zip(*[m.get_maps(x[i:i + 1], normalize=False) for i in range(len(x))])
            q = {}
            for name, maps in (("st", st), ("ae", ae)):
                flat = torch.cat([t.flatten() for t in maps])
                if flat.numel() > 16_000_000:
                    flat = flat[torch.randperm(flat.numel(), device=flat.device)[:16_000_000]]
                q[f"qa_{name}"], q[f"qb_{name}"] = torch.quantile(flat, 0.9), torch.quantile(flat, 0.995)
            m.quantiles.update(q)
        del lm.imagenet_loader
        return m


class Padim(Base):
    norm = True

    def __init__(self, device, size=256):
        super().__init__(device, size)
        self.info = {"backbone": "resnet18", "layers": ["layer1", "layer2", "layer3"], "n_features": 100}

    def fit(self, imgs):
        from anomalib.models.image.padim.torch_model import PadimModel
        m = PadimModel(backbone="resnet18", layers=["layer1", "layer2", "layer3"], pre_trained=True, n_features=100)
        m = m.to(self.device).train()
        x = self.prep(imgs)
        for i in range(0, len(x), 8):
            m(x[i:i + 8].to(self.device))
        m.fit()
        return m.eval()


class Generic(Base):
    """SuperSimpleNet (name 'simplenet'). GLASS is in anomalib 2.7 but needs a DTD texture download; not wired."""
    norm = True

    def __init__(self, name, device, steps=300, size=256):
        super().__init__(device, size)
        if name != "simplenet":
            raise RuntimeError(f"{name}: not wired in this harness")
        self.steps = steps
        self.info = {"model": "SuperSimpleNet (anomalib 2.7)", "backbone": "wide_resnet50_2.tv_in1k",
                     "layers": ["layer2", "layer3"], "steps": steps, "batch": 8, "perlin_threshold": 0.2}

    def fit(self, imgs):
        from anomalib.models.image.supersimplenet.loss import SSNLoss
        from anomalib.models.image.supersimplenet.torch_model import SupersimplenetModel
        m = SupersimplenetModel(perlin_threshold=0.2, backbone="wide_resnet50_2.tv_in1k", layers=["layer2", "layer3"],
                                stop_grad=True, adapt_cls_features=False).to(self.device)
        loss_fn = SSNLoss()
        opt = torch.optim.AdamW([{"params": m.adaptor.parameters(), "lr": 1e-4},
                                 {"params": m.segdec.parameters(), "lr": 2e-4, "weight_decay": 1e-5}])
        sched = torch.optim.lr_scheduler.MultiStepLR(opt, [int(self.steps * 0.8), int(self.steps * 0.9)], gamma=0.4)
        x = self.prep(imgs)
        m.train()
        for _ in range(self.steps):
            idx = [random.randrange(len(x)) for _ in range(min(8, len(x)))]
            xb = x[idx].to(self.device)
            amap, ascore, masks, labels = m(images=xb, masks=None, labels=torch.zeros(len(idx), device=self.device))
            loss = loss_fn(pred_map=amap, pred_score=ascore, target_mask=masks, target_label=labels)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
        return m.eval()
