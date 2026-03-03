/**
 * Shape Pack System — extensible icon/shape registry for node visualization.
 *
 * Built-in packs: Default (geometric), AWS, Kubernetes, Database.
 * Custom packs can be registered via the Plugin API.
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ShapePack {
  /** Unique pack ID */
  id: string;
  /** Display name */
  name: string;
  /** Pack description */
  description: string;
  /** Shapes provided by this pack */
  shapes: ShapeDefinition[];
}

export interface ShapeDefinition {
  /** Shape key (used to match node types) */
  key: string;
  /** Display label */
  label: string;
  /** SVG path data (for 2D fallback / legend) */
  svgPath: string;
  /** SVG viewBox dimensions */
  viewBox: string;
  /** Default color (hex) */
  defaultColor: string;
  /** Tags for matching (e.g., ["compute", "server"]) */
  tags: string[];
}

// ─── Built-in Shape Packs ────────────────────────────────────────────────────

const DEFAULT_PACK: ShapePack = {
  id: "default",
  name: "Default",
  description: "Geometric shapes for code entities",
  shapes: [
    {
      key: "module",
      label: "Module",
      svgPath: "M3 3h18v18H3z",
      viewBox: "0 0 24 24",
      defaultColor: "#10b981",
      tags: ["code", "module", "file"],
    },
    {
      key: "class",
      label: "Class",
      svgPath: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
      viewBox: "0 0 24 24",
      defaultColor: "#6366f1",
      tags: ["code", "class", "object"],
    },
    {
      key: "function",
      label: "Function",
      svgPath: "M12 2a10 10 0 100 20 10 10 0 000-20z",
      viewBox: "0 0 24 24",
      defaultColor: "#f59e0b",
      tags: ["code", "function", "method"],
    },
    {
      key: "interface",
      label: "Interface",
      svgPath: "M12 2l10 6v8l-10 6L2 16V8z",
      viewBox: "0 0 24 24",
      defaultColor: "#06b6d4",
      tags: ["code", "interface", "contract"],
    },
    {
      key: "component",
      label: "Component",
      svgPath: "M12 2L2 7v10l10 5 10-5V7z",
      viewBox: "0 0 24 24",
      defaultColor: "#8b5cf6",
      tags: ["ui", "component", "react"],
    },
    {
      key: "test",
      label: "Test",
      svgPath: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
      viewBox: "0 0 24 24",
      defaultColor: "#22c55e",
      tags: ["test", "spec", "quality"],
    },
  ],
};

const AWS_PACK: ShapePack = {
  id: "aws",
  name: "AWS",
  description: "Amazon Web Services service icons",
  shapes: [
    {
      key: "aws-lambda",
      label: "Lambda",
      svgPath: "M4 20L12 4l8 16H4z",
      viewBox: "0 0 24 24",
      defaultColor: "#FF9900",
      tags: ["aws", "lambda", "serverless", "compute"],
    },
    {
      key: "aws-s3",
      label: "S3",
      svgPath: "M20 16V8l-8-4-8 4v8l8 4 8-4z",
      viewBox: "0 0 24 24",
      defaultColor: "#3F8624",
      tags: ["aws", "s3", "storage", "bucket"],
    },
    {
      key: "aws-ec2",
      label: "EC2",
      svgPath: "M4 4h16v16H4zM8 8h8v8H8z",
      viewBox: "0 0 24 24",
      defaultColor: "#FF9900",
      tags: ["aws", "ec2", "compute", "server"],
    },
    {
      key: "aws-rds",
      label: "RDS",
      svgPath: "M12 2C6.48 2 2 4.69 2 8v8c0 3.31 4.48 6 10 6s10-2.69 10-6V8c0-3.31-4.48-6-10-6z",
      viewBox: "0 0 24 24",
      defaultColor: "#3B48CC",
      tags: ["aws", "rds", "database", "sql"],
    },
    {
      key: "aws-sqs",
      label: "SQS",
      svgPath: "M2 6h20v12H2zM7 6V4h10v2",
      viewBox: "0 0 24 24",
      defaultColor: "#FF4F8B",
      tags: ["aws", "sqs", "queue", "messaging"],
    },
    {
      key: "aws-api-gateway",
      label: "API Gateway",
      svgPath: "M12 2v20M2 12h20M6 6l12 12M18 6L6 18",
      viewBox: "0 0 24 24",
      defaultColor: "#FF4F8B",
      tags: ["aws", "api", "gateway", "rest"],
    },
  ],
};

const K8S_PACK: ShapePack = {
  id: "kubernetes",
  name: "Kubernetes",
  description: "Kubernetes resource icons",
  shapes: [
    {
      key: "k8s-pod",
      label: "Pod",
      svgPath: "M12 2L2 7v10l10 5 10-5V7z",
      viewBox: "0 0 24 24",
      defaultColor: "#326CE5",
      tags: ["k8s", "pod", "container", "compute"],
    },
    {
      key: "k8s-service",
      label: "Service",
      svgPath: "M12 2a10 10 0 100 20 10 10 0 000-20zm0 4a6 6 0 110 12 6 6 0 010-12z",
      viewBox: "0 0 24 24",
      defaultColor: "#326CE5",
      tags: ["k8s", "service", "network", "loadbalancer"],
    },
    {
      key: "k8s-deployment",
      label: "Deployment",
      svgPath: "M4 4h16v16H4zM8 2v4M16 2v4M8 18v4M16 18v4",
      viewBox: "0 0 24 24",
      defaultColor: "#326CE5",
      tags: ["k8s", "deployment", "replica", "rollout"],
    },
    {
      key: "k8s-configmap",
      label: "ConfigMap",
      svgPath: "M4 4h16v16H4zM4 9h16M9 4v16",
      viewBox: "0 0 24 24",
      defaultColor: "#7B68EE",
      tags: ["k8s", "configmap", "config", "settings"],
    },
    {
      key: "k8s-secret",
      label: "Secret",
      svgPath: "M12 2a5 5 0 00-5 5v3H5v12h14V10h-2V7a5 5 0 00-5-5zm0 2a3 3 0 013 3v3H9V7a3 3 0 013-3z",
      viewBox: "0 0 24 24",
      defaultColor: "#FF6347",
      tags: ["k8s", "secret", "security", "credentials"],
    },
    {
      key: "k8s-ingress",
      label: "Ingress",
      svgPath: "M2 12h6l4-8 4 16 4-8h4",
      viewBox: "0 0 24 24",
      defaultColor: "#326CE5",
      tags: ["k8s", "ingress", "network", "route"],
    },
  ],
};

const DB_PACK: ShapePack = {
  id: "database",
  name: "Database",
  description: "Database and storage icons",
  shapes: [
    {
      key: "db-postgres",
      label: "PostgreSQL",
      svgPath: "M12 2C6.48 2 2 4.69 2 8v8c0 3.31 4.48 6 10 6s10-2.69 10-6V8c0-3.31-4.48-6-10-6z",
      viewBox: "0 0 24 24",
      defaultColor: "#336791",
      tags: ["database", "postgres", "sql", "relational"],
    },
    {
      key: "db-redis",
      label: "Redis",
      svgPath: "M2 12l10-6 10 6-10 6-10-6z",
      viewBox: "0 0 24 24",
      defaultColor: "#DC382D",
      tags: ["database", "redis", "cache", "kv"],
    },
    {
      key: "db-mongo",
      label: "MongoDB",
      svgPath: "M12 2c-1 4-4 6-4 11a4 4 0 008 0c0-5-3-7-4-11z",
      viewBox: "0 0 24 24",
      defaultColor: "#47A248",
      tags: ["database", "mongo", "nosql", "document"],
    },
    {
      key: "db-elastic",
      label: "Elasticsearch",
      svgPath: "M2 12a10 10 0 0120 0M2 12a10 10 0 0020 0M7 5h10M7 19h10",
      viewBox: "0 0 24 24",
      defaultColor: "#FEC514",
      tags: ["database", "elastic", "search", "index"],
    },
    {
      key: "db-qdrant",
      label: "Qdrant",
      svgPath: "M12 2l8 4.5v11L12 22l-8-4.5v-11z",
      viewBox: "0 0 24 24",
      defaultColor: "#DC244C",
      tags: ["database", "qdrant", "vector", "embedding"],
    },
    {
      key: "db-neo4j",
      label: "Neo4j",
      svgPath: "M12 8a4 4 0 100-8 4 4 0 000 8zM4 20a4 4 0 100-8 4 4 0 000 8zM20 20a4 4 0 100-8 4 4 0 000 8zM12 8v4M8 14l-4 2M16 14l4 2",
      viewBox: "0 0 24 24",
      defaultColor: "#4581C3",
      tags: ["database", "neo4j", "graph", "knowledge"],
    },
  ],
};

// ─── Shape Pack Registry ─────────────────────────────────────────────────────

const _packs = new Map<string, ShapePack>();

// Register built-in packs
_packs.set(DEFAULT_PACK.id, DEFAULT_PACK);
_packs.set(AWS_PACK.id, AWS_PACK);
_packs.set(K8S_PACK.id, K8S_PACK);
_packs.set(DB_PACK.id, DB_PACK);

/** Register a custom shape pack */
export function registerShapePack(pack: ShapePack): void {
  _packs.set(pack.id, pack);
}

/** Get a shape pack by ID */
export function getShapePack(id: string): ShapePack | undefined {
  return _packs.get(id);
}

/** Get all registered shape packs */
export function getAllShapePacks(): ShapePack[] {
  return Array.from(_packs.values());
}

/** Find the best matching shape for a node type/tags */
export function findShape(
  nodeType: string,
  nodeTags: string[],
  enabledPacks: string[] = ["default"],
): ShapeDefinition | null {
  const lowerType = nodeType.toLowerCase();
  const lowerTags = new Set(nodeTags.map((t) => t.toLowerCase()));

  let bestMatch: ShapeDefinition | null = null;
  let bestScore = 0;

  for (const packId of enabledPacks) {
    const pack = _packs.get(packId);
    if (!pack) continue;

    for (const shape of pack.shapes) {
      let score = 0;

      // Exact key match
      if (shape.key === lowerType) score += 10;

      // Key contains type
      if (shape.key.includes(lowerType) || lowerType.includes(shape.key)) {
        score += 5;
      }

      // Tag overlap
      for (const tag of shape.tags) {
        if (lowerTags.has(tag)) score += 2;
        if (lowerType.includes(tag)) score += 1;
      }

      if (score > bestScore) {
        bestScore = score;
        bestMatch = shape;
      }
    }
  }

  return bestMatch;
}

/** Get a shape's SVG as a data URL (for use as texture/icon) */
export function shapeToDataUrl(
  shape: ShapeDefinition,
  size: number = 64,
  color?: string,
): string {
  const fill = color || shape.defaultColor;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${shape.viewBox}" width="${size}" height="${size}">
    <path d="${shape.svgPath}" fill="none" stroke="${fill}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
