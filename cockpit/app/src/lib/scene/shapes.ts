/* ====== SHAPES -- 26 3D shape builders for the system map ======
   Ported from client/js/scene/shapes.js.
   Each shape is a factory that returns a THREE.Group.
   mkObj(shape, size, matFactory) is the main entry point.       */

import * as THREE from "three";
import { ParametricGeometry } from "three/addons/geometries/ParametricGeometry.js";
import type { MatFactory } from "./materials";

export function mkObj(
  shape: string,
  size: number,
  matFactory: MatFactory,
): THREE.Group {
  const s = size;
  const g = new THREE.Group();

  const M_DARK = () => matFactory.dark();
  const M_MID = () => matFactory.mid();
  const M_LIGHT = () => matFactory.light();
  const M_ACCENT = () => matFactory.accent();
  const M_SCREEN = () => matFactory.screen();
  const _pal = matFactory.palette;

  switch (shape) {
    // ── warehouse ──
    case "warehouse": {
      const cab = new THREE.Mesh(new THREE.BoxGeometry(s * 0.55, s * 0.7, s * 0.45), M_DARK());
      g.add(cab);
      for (let i = 0; i < 4; i++) {
        const dr = new THREE.Mesh(new THREE.BoxGeometry(s * 0.48, s * 0.12, s * 0.02), M_MID());
        dr.position.set(0, s * 0.22 - i * s * 0.16, s * 0.235);
        g.add(dr);
        const hdl = new THREE.Mesh(new THREE.BoxGeometry(s * 0.15, s * 0.02, s * 0.03), M_LIGHT());
        hdl.position.set(0, s * 0.22 - i * s * 0.16, s * 0.26);
        g.add(hdl);
      }
      const top = new THREE.Mesh(new THREE.BoxGeometry(s * 0.58, s * 0.03, s * 0.48), M_ACCENT());
      top.position.y = s * 0.365;
      g.add(top);
      break;
    }

    // ── factory ──
    case "factory": {
      const base = new THREE.Mesh(new THREE.BoxGeometry(s * 0.6, s * 0.1, s * 0.5), M_DARK());
      base.position.y = -s * 0.15;
      g.add(base);
      const tower = new THREE.Mesh(new THREE.BoxGeometry(s * 0.08, s * 0.6, s * 0.08), M_MID());
      tower.position.set(s * 0.1, s * 0.15, 0);
      g.add(tower);
      const cross1 = new THREE.Mesh(new THREE.BoxGeometry(s * 0.25, s * 0.03, s * 0.03), M_ACCENT());
      cross1.position.set(s * 0.1, s * 0.35, 0);
      g.add(cross1);
      const cross2 = new THREE.Mesh(new THREE.BoxGeometry(s * 0.2, s * 0.03, s * 0.03), M_ACCENT());
      cross2.position.set(s * 0.1, s * 0.15, 0);
      g.add(cross2);
      const drill = new THREE.Mesh(new THREE.ConeGeometry(s * 0.04, s * 0.18, 8), M_LIGHT());
      drill.position.set(s * 0.1, -s * 0.18, 0);
      drill.rotation.x = Math.PI;
      g.add(drill);
      const pipe = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.015, s * 0.015, s * 0.25, 8), M_ACCENT());
      pipe.position.set(s * 0.1, -s * 0.02, 0);
      g.add(pipe);
      const ctrl = new THREE.Mesh(new THREE.BoxGeometry(s * 0.2, s * 0.2, s * 0.18), M_DARK());
      ctrl.position.set(-s * 0.18, 0, 0);
      g.add(ctrl);
      const screen = new THREE.Mesh(new THREE.PlaneGeometry(s * 0.14, s * 0.1), M_SCREEN());
      screen.position.set(-s * 0.18, s * 0.04, s * 0.1);
      g.add(screen);
      break;
    }

    // ── satellite ──
    case "satellite": {
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.06, s * 0.1, s * 0.5, 8), M_DARK());
      g.add(pole);
      const dish = new THREE.Mesh(
        new THREE.SphereGeometry(s * 0.32, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.45), M_MID());
      dish.rotation.x = Math.PI * 0.2;
      dish.position.y = s * 0.3;
      g.add(dish);
      const feed = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.015, s * 0.015, s * 0.4, 8), M_ACCENT());
      feed.position.set(0, s * 0.45, -s * 0.1);
      feed.rotation.x = 0.3;
      g.add(feed);
      const tip = new THREE.Mesh(new THREE.SphereGeometry(s * 0.04, 8, 8), M_LIGHT());
      tip.position.set(0, s * 0.62, -s * 0.2);
      g.add(tip);
      break;
    }

    // ── terminal ──
    case "terminal": {
      const spine = new THREE.Mesh(new THREE.BoxGeometry(s * 0.08, s * 0.08, s * 0.45), M_DARK());
      g.add(spine);
      const pageL = new THREE.Mesh(new THREE.BoxGeometry(s * 0.32, s * 0.04, s * 0.42), M_MID());
      pageL.position.set(-s * 0.19, s * 0.02, 0);
      pageL.rotation.z = 0.08;
      g.add(pageL);
      const pageR = new THREE.Mesh(new THREE.BoxGeometry(s * 0.32, s * 0.04, s * 0.42), M_MID());
      pageR.position.set(s * 0.19, s * 0.02, 0);
      pageR.rotation.z = -0.08;
      g.add(pageR);
      for (let i = 0; i < 5; i++) {
        const w = s * (0.12 + Math.random() * 0.1);
        const lineL = new THREE.Mesh(new THREE.BoxGeometry(w, s * 0.008, s * 0.01), M_ACCENT());
        lineL.position.set(-s * 0.2 + s * 0.02, s * 0.05, -s * 0.12 + i * s * 0.07);
        g.add(lineL);
        const lineR = new THREE.Mesh(new THREE.BoxGeometry(w, s * 0.008, s * 0.01), M_ACCENT());
        lineR.position.set(s * 0.2 - s * 0.02, s * 0.05, -s * 0.12 + i * s * 0.07);
        g.add(lineR);
      }
      const pen = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.01, s * 0.008, s * 0.25, 8), M_LIGHT());
      pen.position.set(s * 0.3, s * 0.08, s * 0.1);
      pen.rotation.z = -0.3;
      pen.rotation.x = 0.2;
      g.add(pen);
      break;
    }

    // ── monument ──
    case "monument": {
      for (let i = 0; i < 4; i++) {
        const w = s * (0.7 - i * 0.14), h = s * 0.14;
        const tier = new THREE.Mesh(new THREE.BoxGeometry(w, h, w), i < 2 ? M_DARK() : M_MID());
        tier.position.y = i * s * 0.15;
        g.add(tier);
      }
      const cap = new THREE.Mesh(new THREE.ConeGeometry(s * 0.12, s * 0.15, 4), M_LIGHT());
      cap.position.y = s * 0.65;
      cap.rotation.y = Math.PI / 4;
      g.add(cap);
      break;
    }

    // ── pillars ──
    case "pillars": {
      const base = new THREE.Mesh(new THREE.BoxGeometry(s * 0.8, s * 0.06, s * 0.35), M_DARK());
      base.position.y = -s * 0.18;
      g.add(base);
      for (let i = 0; i < 3; i++) {
        const col = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.045, s * 0.055, s * 0.45, 8), M_MID());
        col.position.set((i - 1) * s * 0.28, s * 0.05, 0);
        g.add(col);
      }
      const entab = new THREE.Mesh(new THREE.BoxGeometry(s * 0.85, s * 0.07, s * 0.38), M_LIGHT());
      entab.position.y = s * 0.31;
      g.add(entab);
      const ped = new THREE.Mesh(new THREE.ConeGeometry(s * 0.42, s * 0.12, 3), M_ACCENT());
      ped.position.y = s * 0.42;
      g.add(ped);
      break;
    }

    // ── gear ──
    case "gear": {
      const g1 = new THREE.Mesh(new THREE.TorusGeometry(s * 0.28, s * 0.08, 8, 20), M_MID());
      g1.rotation.x = Math.PI / 2;
      g1.userData.animate = "gear_main";
      g.add(g1);
      const g2 = new THREE.Mesh(new THREE.TorusGeometry(s * 0.18, s * 0.06, 8, 16), M_DARK());
      g2.rotation.x = Math.PI / 2;
      g2.position.set(s * 0.3, s * 0.05, 0);
      g2.userData.animate = "gear_secondary";
      g.add(g2);
      const axle = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.04, s * 0.04, s * 0.2, 8), M_ACCENT());
      g.add(axle);
      const axle2 = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.03, s * 0.03, s * 0.15, 8), M_ACCENT());
      axle2.position.set(s * 0.3, s * 0.05, 0);
      g.add(axle2);
      break;
    }

    // ── gate ──
    case "gate": {
      const body = new THREE.Mesh(new THREE.BoxGeometry(s * 0.45, s * 0.35, s * 0.2), M_DARK());
      body.position.y = -s * 0.08;
      g.add(body);
      const topR = new THREE.Mesh(
        new THREE.CylinderGeometry(s * 0.225, s * 0.225, s * 0.2, 16, 1, false, 0, Math.PI), M_DARK());
      topR.rotation.z = Math.PI / 2;
      topR.rotation.y = Math.PI / 2;
      topR.position.y = s * 0.1;
      g.add(topR);
      const shackle = new THREE.Mesh(new THREE.TorusGeometry(s * 0.15, s * 0.03, 8, 16, Math.PI), M_LIGHT());
      shackle.position.y = s * 0.22;
      g.add(shackle);
      const legL = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.03, s * 0.03, s * 0.12, 8), M_LIGHT());
      legL.position.set(-s * 0.15, s * 0.16, 0);
      g.add(legL);
      const legR = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.03, s * 0.03, s * 0.12, 8), M_LIGHT());
      legR.position.set(s * 0.15, s * 0.16, 0);
      g.add(legR);
      const keyH = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.035, s * 0.035, s * 0.02, 8), M_SCREEN());
      keyH.position.set(0, -s * 0.1, s * 0.11);
      keyH.rotation.x = Math.PI / 2;
      g.add(keyH);
      const keySlit = new THREE.Mesh(new THREE.BoxGeometry(s * 0.02, s * 0.06, s * 0.02), M_SCREEN());
      keySlit.position.set(0, -s * 0.14, s * 0.11);
      g.add(keySlit);
      break;
    }

    // ── database ──
    case "database": {
      for (let i = 0; i < 3; i++) {
        const c = new THREE.Mesh(
          new THREE.CylinderGeometry(s * 0.3, s * 0.3, s * 0.12, 12), i === 1 ? M_MID() : M_DARK());
        c.position.y = i * s * 0.16 - s * 0.1;
        g.add(c);
      }
      break;
    }

    // ── hourglass ──
    case "hourglass": {
      for (const dx of [-1, 1]) {
        const p = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.02, s * 0.02, s * 0.65, 8), M_ACCENT());
        p.position.x = dx * s * 0.22;
        g.add(p);
      }
      const topCap = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.24, s * 0.24, s * 0.03, 8), M_LIGHT());
      topCap.position.y = s * 0.32;
      g.add(topCap);
      const botCap = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.24, s * 0.24, s * 0.03, 8), M_LIGHT());
      botCap.position.y = -s * 0.32;
      g.add(botCap);
      const topBulb = new THREE.Mesh(new THREE.ConeGeometry(s * 0.2, s * 0.28, 8), M_MID());
      topBulb.position.y = s * 0.14;
      topBulb.rotation.x = Math.PI;
      g.add(topBulb);
      const botBulb = new THREE.Mesh(new THREE.ConeGeometry(s * 0.2, s * 0.28, 8), M_DARK());
      botBulb.position.y = -s * 0.14;
      g.add(botBulb);
      const neck = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.03, s * 0.03, s * 0.08, 8), M_ACCENT());
      neck.userData.animate = "hg_neck";
      g.add(neck);
      break;
    }

    // ── brain ──
    case "brain": {
      const gemPts = [
        new THREE.Vector2(0, s * 0.22),
        new THREE.Vector2(s * 0.16, s * 0.06),
        new THREE.Vector2(s * 0.2, 0),
        new THREE.Vector2(s * 0.12, -s * 0.1),
        new THREE.Vector2(0, -s * 0.18),
      ];
      const gemGeo = new THREE.LatheGeometry(gemPts, 16);
      const crystal = new THREE.Mesh(gemGeo, new THREE.MeshStandardMaterial({
        color: _pal.m, metalness: 0.3, roughness: 0.15,
        emissive: new THREE.Color(_pal.a), emissiveIntensity: 0.08,
      }));
      g.add(crystal);
      const core = new THREE.Mesh(
        new THREE.IcosahedronGeometry(s * 0.08, 1),
        new THREE.MeshStandardMaterial({
          color: _pal.l, metalness: 0.25, roughness: 0.45,
          emissive: new THREE.Color(_pal.a), emissiveIntensity: 0.2,
        }));
      g.add(core);
      const R = s * 0.38, Wb = s * 0.07;
      const mFn = (u: number, t: number, tgt: THREE.Vector3) => {
        u *= Math.PI * 2;
        t = t * 2 - 1;
        tgt.set(
          (R + Wb * t * Math.cos(u / 2)) * Math.cos(u),
          Wb * t * Math.sin(u / 2),
          (R + Wb * t * Math.cos(u / 2)) * Math.sin(u),
        );
      };
      const mGeo = new ParametricGeometry(mFn, 48, 6);
      const strip = new THREE.Mesh(mGeo, new THREE.MeshStandardMaterial({
        color: _pal.d, metalness: 0.3, roughness: 0.55, side: THREE.DoubleSide,
      }));
      strip.rotation.z = Math.PI * 0.06;
      g.add(strip);
      break;
    }

    // ── dyson_book ──
    case "dyson_book": {
      const pedGeo = new THREE.CylinderGeometry(s * 0.22, s * 0.26, s * 0.08, 16);
      g.add(new THREE.Mesh(pedGeo, M_DARK()));
      const pedRim = new THREE.Mesh(new THREE.TorusGeometry(s * 0.24, s * 0.012, 8, 20), M_MID());
      pedRim.rotation.x = Math.PI / 2;
      pedRim.position.y = s * 0.04;
      g.add(pedRim);
      const bookSpine = new THREE.Mesh(new THREE.BoxGeometry(s * 0.05, s * 0.4, s * 0.32), M_DARK());
      bookSpine.position.y = s * 0.08;
      g.add(bookSpine);
      const pgLGeo = new THREE.BoxGeometry(s * 0.26, s * 0.38, s * 0.015, 8, 1, 1);
      const pgLPos = pgLGeo.attributes.position;
      for (let vi = 0; vi < pgLPos.count; vi++) {
        const px = pgLPos.getX(vi);
        const curl = Math.sin((-px / (s * 0.26) + 0.5) * Math.PI * 0.4) * s * 0.015;
        pgLPos.setZ(vi, pgLPos.getZ(vi) + curl);
      }
      pgLGeo.computeVertexNormals();
      const pageL = new THREE.Mesh(pgLGeo, M_LIGHT());
      pageL.position.set(-s * 0.16, s * 0.08, 0);
      pageL.rotation.y = Math.PI * 0.06;
      g.add(pageL);
      const pgRGeo = new THREE.BoxGeometry(s * 0.26, s * 0.38, s * 0.015, 8, 1, 1);
      const pgRPos = pgRGeo.attributes.position;
      for (let vi = 0; vi < pgRPos.count; vi++) {
        const px = pgRPos.getX(vi);
        const curl = Math.sin((px / (s * 0.26) + 0.5) * Math.PI * 0.4) * s * 0.015;
        pgRPos.setZ(vi, pgRPos.getZ(vi) + curl);
      }
      pgRGeo.computeVertexNormals();
      const pageR = new THREE.Mesh(pgRGeo, M_LIGHT());
      pageR.position.set(s * 0.16, s * 0.08, 0);
      pageR.rotation.y = -Math.PI * 0.06;
      g.add(pageR);
      for (let i = 0; i < 4; i++) {
        const tl = new THREE.Mesh(
          new THREE.BoxGeometry(s * (0.1 + Math.random() * 0.08), s * 0.01, s * 0.002), M_MID());
        tl.position.set(-s * 0.16, s * 0.18 - i * s * 0.065 + s * 0.08, s * 0.012);
        g.add(tl);
      }
      for (let i = 0; i < 4; i++) {
        const tr = new THREE.Mesh(
          new THREE.BoxGeometry(s * (0.1 + Math.random() * 0.08), s * 0.01, s * 0.002), M_MID());
        tr.position.set(s * 0.16, s * 0.18 - i * s * 0.065 + s * 0.08, s * 0.012);
        g.add(tr);
      }
      const dY = s * 0.55;
      const dCore = new THREE.Mesh(
        new THREE.SphereGeometry(s * 0.18, 16, 12),
        new THREE.MeshStandardMaterial({ color: _pal.m, metalness: 0.3, roughness: 0.5 }));
      dCore.position.y = dY;
      g.add(dCore);
      const dInner = new THREE.Mesh(
        new THREE.SphereGeometry(s * 0.09, 8, 8),
        new THREE.MeshStandardMaterial({
          color: _pal.l, metalness: 0.25, roughness: 0.45,
          emissive: new THREE.Color(_pal.a), emissiveIntensity: 0.25,
        }));
      dInner.position.y = dY;
      g.add(dInner);
      break;
    }

    // ── gauge ──
    case "gauge": {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(s * 0.32, s * 0.06, 8, 20), M_DARK());
      ring.rotation.x = Math.PI / 2;
      g.add(ring);
      const face = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.28, s * 0.28, s * 0.03, 16), M_MID());
      g.add(face);
      const needle = new THREE.Mesh(new THREE.BoxGeometry(s * 0.03, s * 0.04, s * 0.28), M_ACCENT());
      needle.position.z = s * 0.08;
      needle.rotation.z = Math.PI / 5;
      g.add(needle);
      const hubM = new THREE.Mesh(new THREE.SphereGeometry(s * 0.06, 8, 8), M_LIGHT());
      g.add(hubM);
      break;
    }

    // ── hub ──
    case "hub": {
      const center = new THREE.Mesh(new THREE.DodecahedronGeometry(s * 0.28), M_MID());
      center.userData.animate = "hub_core";
      g.add(center);
      for (let i = 0; i < 6; i++) {
        const a = (i * Math.PI) / 3;
        const arm = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.025, s * 0.025, s * 0.3, 8), M_ACCENT());
        arm.rotation.z = Math.PI / 2;
        arm.position.set(Math.cos(a) * s * 0.25, 0, Math.sin(a) * s * 0.25);
        arm.rotation.y = a;
        g.add(arm);
        const tipM = new THREE.Mesh(new THREE.SphereGeometry(s * 0.05, 8, 8), M_LIGHT());
        tipM.position.set(Math.cos(a) * s * 0.42, 0, Math.sin(a) * s * 0.42);
        g.add(tipM);
      }
      break;
    }

    // ── tree ──
    case "tree": {
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.05, s * 0.08, s * 0.4, 8), M_DARK());
      g.add(trunk);
      const crown = new THREE.Mesh(new THREE.IcosahedronGeometry(s * 0.28, 0), M_MID());
      crown.position.y = s * 0.35;
      g.add(crown);
      for (let i = -1; i <= 1; i += 2) {
        const branch = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.02, s * 0.03, s * 0.25, 8), M_ACCENT());
        branch.position.set(i * s * 0.15, s * 0.15, 0);
        branch.rotation.z = -i * 0.5;
        g.add(branch);
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(s * 0.1, 8, 8), M_MID());
        leaf.position.set(i * s * 0.3, s * 0.28, 0);
        g.add(leaf);
      }
      break;
    }

    // ── sphere ──
    case "sphere": {
      const sp = new THREE.Mesh(new THREE.SphereGeometry(s * 0.32, 16, 12), M_MID());
      g.add(sp);
      const r1 = new THREE.Mesh(new THREE.TorusGeometry(s * 0.42, s * 0.015, 8, 24), M_ACCENT());
      r1.rotation.x = Math.PI / 3;
      g.add(r1);
      const r2 = new THREE.Mesh(new THREE.TorusGeometry(s * 0.38, s * 0.012, 8, 24), M_DARK());
      r2.rotation.y = Math.PI / 2.5;
      r2.rotation.z = Math.PI / 4;
      g.add(r2);
      break;
    }

    // ── prism ──
    case "prism": {
      const rough = new THREE.Mesh(new THREE.DodecahedronGeometry(s * 0.22, 0), M_DARK());
      rough.position.set(-s * 0.15, -s * 0.08, 0);
      g.add(rough);
      const prismG = new THREE.CylinderGeometry(s * 0.18, s * 0.22, s * 0.5, 8);
      const prismM = new THREE.Mesh(prismG, M_LIGHT());
      prismM.position.set(s * 0.08, s * 0.05, 0);
      prismM.userData.animate = "prism_polished";
      g.add(prismM);
      for (let i = 0; i < 3; i++) {
        const spark = new THREE.Mesh(new THREE.OctahedronGeometry(s * 0.04), M_ACCENT());
        spark.position.set(
          s * 0.2 + Math.random() * s * 0.1,
          s * 0.25 + i * s * 0.08,
          Math.random() * s * 0.1 - 0.05);
        g.add(spark);
      }
      break;
    }

    // ── stairs ──
    case "stairs": {
      for (let i = 0; i < 5; i++) {
        const step = new THREE.Mesh(
          new THREE.BoxGeometry(s * (0.55 - i * 0.04), s * 0.08, s * 0.3), i < 3 ? M_DARK() : M_MID());
        step.position.set(i * s * 0.12 - s * 0.24, i * s * 0.1 - s * 0.15, 0);
        g.add(step);
      }
      const arrow = new THREE.Mesh(new THREE.ConeGeometry(s * 0.1, s * 0.15, 3), M_LIGHT());
      arrow.position.set(s * 0.3, s * 0.35, 0);
      g.add(arrow);
      break;
    }

    // ── nexus ──
    case "nexus": {
      for (let ly = 0; ly < 3; ly++) {
        const plate = new THREE.Mesh(
          new THREE.BoxGeometry(s * 0.6, s * 0.03, s * 0.35), ly === 1 ? M_MID() : M_DARK());
        plate.position.y = ly * s * 0.2 - s * 0.15;
        g.add(plate);
        for (let nx = 0; nx < 2; nx++) {
          const node = new THREE.Mesh(new THREE.SphereGeometry(s * 0.05, 8, 8), M_LIGHT());
          node.position.set((nx - 0.5) * s * 0.3, ly * s * 0.2 - s * 0.1, 0);
          g.add(node);
        }
      }
      for (let i = 0; i < 3; i++) {
        const conn = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.012, s * 0.012, s * 0.45, 8), M_ACCENT());
        conn.position.set((i - 1) * s * 0.2, s * 0.08, 0);
        g.add(conn);
      }
      break;
    }

    // ── graph ──
    case "graph": {
      const positions: [number, number, number][] = [
        [0, s * 0.15, 0],
        [-s * 0.2, -s * 0.1, -s * 0.1],
        [s * 0.2, -s * 0.1, s * 0.1],
        [s * 0.15, s * 0.1, -s * 0.15],
        [-s * 0.1, -0.05, s * 0.15],
      ];
      positions.forEach(([px, py, pz], i) => {
        const n = new THREE.Mesh(
          new THREE.SphereGeometry(i === 0 ? s * 0.1 : s * 0.07, 8, 8),
          i === 0 ? M_LIGHT() : M_MID());
        n.position.set(px, py, pz);
        g.add(n);
      });
      const links: [number, number][] = [[0, 1], [0, 2], [0, 3], [1, 4], [2, 3], [3, 4]];
      links.forEach(([a, b]) => {
        const pa = positions[a], pb = positions[b];
        const dir = new THREE.Vector3(pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]);
        const len = dir.length();
        dir.normalize();
        const cyl = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.01, s * 0.01, len, 8), M_ACCENT());
        cyl.position.set((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2);
        cyl.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        g.add(cyl);
      });
      break;
    }

    // ── dial ──
    case "dial": {
      const base = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.32, s * 0.35, s * 0.18, 16), M_DARK());
      g.add(base);
      const knob = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.2, s * 0.2, s * 0.1, 12), M_MID());
      knob.position.y = s * 0.14;
      g.add(knob);
      const indicator = new THREE.Mesh(new THREE.BoxGeometry(s * 0.04, s * 0.08, s * 0.22), M_LIGHT());
      indicator.position.set(0, s * 0.22, s * 0.05);
      indicator.userData.animate = "dial_indicator";
      g.add(indicator);
      for (let i = 0; i < 8; i++) {
        const a = (i * Math.PI) / 4;
        const tick = new THREE.Mesh(new THREE.BoxGeometry(s * 0.02, s * 0.04, s * 0.06), M_ACCENT());
        tick.position.set(Math.cos(a) * s * 0.28, s * 0.14, Math.sin(a) * s * 0.28);
        tick.rotation.y = -a;
        g.add(tick);
      }
      break;
    }

    // ── vault ──
    case "vault": {
      const body = new THREE.Mesh(new THREE.BoxGeometry(s * 0.6, s * 0.55, s * 0.5), M_DARK());
      g.add(body);
      const door = new THREE.Mesh(new THREE.BoxGeometry(s * 0.45, s * 0.4, s * 0.02), M_MID());
      door.position.z = s * 0.26;
      g.add(door);
      const lockRing = new THREE.Mesh(new THREE.TorusGeometry(s * 0.1, s * 0.02, 8, 16), M_LIGHT());
      lockRing.position.set(0, 0, s * 0.28);
      g.add(lockRing);
      const lockCenter = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.04, s * 0.04, s * 0.03, 8), M_ACCENT());
      lockCenter.position.set(0, 0, s * 0.29);
      lockCenter.rotation.x = Math.PI / 2;
      g.add(lockCenter);
      const handle = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.02, s * 0.02, s * 0.2, 8), M_ACCENT());
      handle.position.set(s * 0.18, 0, s * 0.28);
      handle.rotation.z = Math.PI / 2;
      g.add(handle);
      const boltPositions: [number, number][] = [[-0.18, 0.16], [0.18, 0.16], [-0.18, -0.16], [0.18, -0.16]];
      for (const [bx, by] of boltPositions) {
        const bolt = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.02, s * 0.02, s * 0.04, 8), M_LIGHT());
        bolt.position.set(bx * s, by * s, s * 0.27);
        bolt.rotation.x = Math.PI / 2;
        g.add(bolt);
      }
      break;
    }

    // ── screens ──
    case "screens": {
      for (let i = -1; i <= 1; i++) {
        const fr = new THREE.Mesh(new THREE.BoxGeometry(s * 0.38, s * 0.3, s * 0.05), M_DARK());
        fr.position.set(i * s * 0.28, s * 0.08, 0);
        fr.rotation.y = i * -0.2;
        g.add(fr);
        const faceM = new THREE.Mesh(new THREE.PlaneGeometry(s * 0.3, s * 0.22), M_SCREEN());
        faceM.position.set(i * s * 0.28, s * 0.08, s * 0.028);
        faceM.rotation.y = i * -0.2;
        g.add(faceM);
      }
      const stand = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.04, s * 0.06, s * 0.22, 8), M_ACCENT());
      stand.position.y = -s * 0.15;
      g.add(stand);
      const base = new THREE.Mesh(new THREE.BoxGeometry(s * 0.5, s * 0.03, s * 0.2), M_MID());
      base.position.y = -s * 0.26;
      g.add(base);
      break;
    }

    // ── rack ──
    case "rack": {
      const frame = new THREE.Mesh(new THREE.BoxGeometry(s * 0.5, s * 0.65, s * 0.4), M_DARK());
      g.add(frame);
      for (let i = 0; i < 5; i++) {
        const unit = new THREE.Mesh(
          new THREE.BoxGeometry(s * 0.44, s * 0.08, s * 0.35), i % 2 === 0 ? M_MID() : M_DARK());
        unit.position.y = i * s * 0.11 - s * 0.22;
        unit.position.z = s * 0.02;
        g.add(unit);
        const led = new THREE.Mesh(
          new THREE.SphereGeometry(s * 0.015, 12, 12),
          new THREE.MeshBasicMaterial({ color: 0x34d399 }));
        led.position.set(s * 0.18, i * s * 0.11 - s * 0.22, s * 0.2);
        g.add(led);
      }
      break;
    }

    // ── conveyor ──
    case "conveyor": {
      const belt = new THREE.Mesh(new THREE.BoxGeometry(s * 0.8, s * 0.06, s * 0.35), M_DARK());
      belt.position.y = -s * 0.1;
      g.add(belt);
      for (const rx of [-s * 0.32, 0, s * 0.32]) {
        const roller = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.06, s * 0.06, s * 0.38, 8), M_MID());
        roller.rotation.x = Math.PI / 2;
        roller.position.set(rx, -s * 0.06, 0);
        g.add(roller);
      }
      for (let i = 0; i < 3; i++) {
        const item = new THREE.Mesh(new THREE.BoxGeometry(s * 0.12, s * 0.1, s * 0.15), M_LIGHT());
        item.position.set(-s * 0.25 + i * s * 0.25, s * 0.02, 0);
        item.userData.animate = "conv_item";
        item.userData.convIdx = i;
        g.add(item);
      }
      const arr = new THREE.Mesh(new THREE.ConeGeometry(s * 0.08, s * 0.12, 3), M_ACCENT());
      arr.position.set(s * 0.45, s * 0.05, 0);
      arr.rotation.z = -Math.PI / 2;
      g.add(arr);
      break;
    }

    // ── monitor ──
    case "monitor": {
      const scrF = new THREE.Mesh(new THREE.BoxGeometry(s * 0.7, s * 0.48, s * 0.05), M_DARK());
      scrF.position.y = s * 0.1;
      g.add(scrF);
      const scrD = new THREE.Mesh(new THREE.PlaneGeometry(s * 0.58, s * 0.38), M_SCREEN());
      scrD.position.set(0, s * 0.1, s * 0.03);
      g.add(scrD);
      for (let i = 0; i < 4; i++) {
        const line = new THREE.Mesh(
          new THREE.BoxGeometry(s * (0.3 + Math.random() * 0.15), s * 0.015, s * 0.001),
          new THREE.MeshBasicMaterial({ color: 0x2a3a5a }));
        line.position.set(-s * 0.05, s * 0.18 - i * s * 0.06, s * 0.032);
        g.add(line);
      }
      const standM = new THREE.Mesh(new THREE.BoxGeometry(s * 0.08, s * 0.2, s * 0.1), M_ACCENT());
      standM.position.y = -s * 0.14;
      g.add(standM);
      const baseM = new THREE.Mesh(new THREE.BoxGeometry(s * 0.35, s * 0.03, s * 0.18), M_MID());
      baseM.position.y = -s * 0.25;
      g.add(baseM);
      break;
    }

    // ── default fallback ──
    default: {
      g.add(new THREE.Mesh(new THREE.BoxGeometry(s * 0.5, s * 0.5, s * 0.5), M_DARK()));
    }
  }

  return g;
}
