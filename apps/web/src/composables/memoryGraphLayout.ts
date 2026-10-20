import type { MemoryGraphData } from './useApi';

/** Deterministic bounded layout. No animation loop or private graph retained outside the view. */
export function memoryGraphLayout(graph: MemoryGraphData) {
  const nodes = graph.nodes.map((node, index) => ({
    ...node, x: 450 + Math.cos(index * 2.39996) * (80 + index * 2),
    y: 260 + Math.sin(index * 2.39996) * (60 + index),
  }));
  const byId = new Map(nodes.map(node => [node.id, node]));
  for (let step = 0; step < 140; step++) {
    const forces = nodes.map(() => ({ x: 0, y: 0 }));
    const indices = new Map(nodes.map((node, index) => [node.id, index]));
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x || .01;
        const dy = nodes[i].y - nodes[j].y || .01;
        const squared = Math.max(100, dx * dx + dy * dy);
        const force = Math.min(10, 1600 / squared);
        const distance = Math.sqrt(squared);
        forces[i].x += dx / distance * force;
        forces[i].y += dy / distance * force;
        forces[j].x -= dx / distance * force;
        forces[j].y -= dy / distance * force;
      }
    }
    for (const edge of graph.edges) {
      const a = indices.get(edge.source), b = indices.get(edge.target);
      if (a === undefined || b === undefined) continue;
      const dx = nodes[b].x - nodes[a].x, dy = nodes[b].y - nodes[a].y;
      const distance = Math.hypot(dx, dy) || 1;
      const force = (distance - 100) * .012;
      forces[a].x += dx / distance * force;
      forces[a].y += dy / distance * force;
      forces[b].x -= dx / distance * force;
      forces[b].y -= dy / distance * force;
    }
    nodes.forEach((node, index) => {
      node.x = Math.max(85, Math.min(815, node.x + forces[index].x + (450 - node.x) * .004));
      node.y = Math.max(45, Math.min(475, node.y + forces[index].y + (260 - node.y) * .004));
    });
  }
  if (nodes.length) {
    const xs = nodes.map(node => node.x), ys = nodes.map(node => node.y);
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    const scale = Math.min(700 / Math.max(100, right - left), 350 / Math.max(100, bottom - top));
    nodes.forEach(node => {
      node.x = 450 + (node.x - (left + right) / 2) * scale;
      node.y = 270 + (node.y - (top + bottom) / 2) * scale;
    });
  }
  return { nodes, edges: graph.edges.flatMap(edge => {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    return source && target ? [{ ...edge, a: source, b: target }] : [];
  }) };
}
