/* Screen-space motion shared by the bounded knowledge graph renderer. */
(() => {
  function advanceAxis(position, velocity, elapsed, minimum, maximum) {
    const span = maximum - minimum;
    if (span <= 0) return { position: (minimum + maximum) / 2, velocity: 0 };
    const start = Math.max(minimum, Math.min(maximum, position));
    const travel = start - minimum + velocity * elapsed;
    const period = 2 * span;
    const phase = ((travel % period) + period) % period;
    let nextVelocity = phase <= span ? velocity : -velocity;
    if (phase === 0) nextVelocity = Math.abs(velocity);
    if (phase === span) nextVelocity = -Math.abs(velocity);
    // A tiny residual speed otherwise leaves a dragged node hugging the wall.
    // Give wall impacts enough inward momentum to produce a visible rebound.
    if (travel <= 0 || travel >= span) {
      const direction = phase === span || nextVelocity < 0 ? -1 : 1;
      nextVelocity = direction * Math.max(30, Math.abs(nextVelocity));
    }
    return {
      position: minimum + (phase <= span ? phase : period - phase),
      velocity: nextVelocity,
    };
  }

  function resolveCollisions(nodes, positions, velocities, pinnedId, scale) {
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i], b = nodes[j];
        const first = positions.get(a.id), second = positions.get(b.id);
        if (!first || !second) continue;
        const dx = second.x - first.x, dy = second.y - first.y;
        const distance = Math.hypot(dx, dy);
        const separation = ((Number(a.size) || 20) + (Number(b.size) || 20)) * scale;
        if (distance >= separation) continue;
        const nx = distance > 0.001 ? dx / distance : 1;
        const ny = distance > 0.001 ? dy / distance : 0;
        const inverseA = a.id === pinnedId ? 0 : 1;
        const inverseB = b.id === pinnedId ? 0 : 1;
        const totalInverseMass = inverseA + inverseB;
        if (!totalInverseMass) continue;
        const correction = (separation - distance + 0.5) / totalInverseMass;
        first.x -= nx * correction * inverseA;
        first.y -= ny * correction * inverseA;
        second.x += nx * correction * inverseB;
        second.y += ny * correction * inverseB;
        const va = inverseA ? (velocities.get(a.id) || { x: 0, y: 0 }) : { x: 0, y: 0 };
        const vb = inverseB ? (velocities.get(b.id) || { x: 0, y: 0 }) : { x: 0, y: 0 };
        const closingSpeed = (vb.x - va.x) * nx + (vb.y - va.y) * ny;
        if (closingSpeed >= 0) continue;
        // Equal-mass impulse with restitution 0.9: bounce without gaining energy.
        const impulse = -1.9 * closingSpeed / totalInverseMass;
        if (inverseA) {
          va.x -= impulse * nx;
          va.y -= impulse * ny;
          velocities.set(a.id, va);
        }
        if (inverseB) {
          vb.x += impulse * nx;
          vb.y += impulse * ny;
          velocities.set(b.id, vb);
        }
      }
    }
  }

  window.ExamGraphPhysics = { advanceAxis, resolveCollisions };
})();
