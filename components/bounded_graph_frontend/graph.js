(() => {
  const frame = document.getElementById("graph-frame");
  const host = document.getElementById("network");
  const loadError = document.getElementById("load-error");
  const velocities = new Map();
  let network = null;
  let nodeData = null;
  let edgeData = null;
  let sourceNodes = [];
  let renderedGraph = "";
  let selectedNode = null;
  let draggedNode = null;
  let animationFrame = null;
  let lastFrameTime = 0;

  function postMessage(type, data = {}) {
    window.parent.postMessage(
      { isStreamlitMessage: true, type, ...data },
      "*",
    );
  }

  function setValue(value) {
    if (value === selectedNode) return;
    selectedNode = value;
    postMessage("streamlit:setComponentValue", { value });
  }

  function hashId(id) {
    let value = 2166136261;
    for (const character of String(id)) {
      value ^= character.charCodeAt(0);
      value = Math.imul(value, 16777619);
    }
    return value >>> 0;
  }

  function startingVelocity(id) {
    const hash = hashId(id);
    const horizontalSpeed = 24 + ((hash >>> 3) % 22);
    const verticalSpeed = 21 + ((hash >>> 8) % 20);
    return {
      x: hash & 1 ? horizontalSpeed : -horizontalSpeed,
      y: hash & 2 ? verticalSpeed : -verticalSpeed,
    };
  }

  function measureTextContext() {
    return document.createElement("canvas").getContext("2d");
  }

  function getNodeFont(node, context) {
    const font = typeof node.font === "object" ? node.font : {};
    const size = Number(font.size) || 16;
    const face = font.face || "Arial";
    context.font = `${font.style || "normal"} ${font.weight || "normal"} ${size}px ${face}`;
    return { size, face };
  }

  function fitNodeLabels(nodes, width) {
    const measure = measureTextContext();
    return nodes.map((node) => {
      const label = String(node.label || "");
      const font = getNodeFont(node, measure);
      const maxWidth = Math.max(80, Math.min(width * 0.65, width - 24));
      const lines = [];
      let line = "";

      for (const word of label.split(/\s+/)) {
        const candidate = line ? `${line} ${word}` : word;
        if (line && measure.measureText(candidate).width > maxWidth) {
          lines.push(line);
          line = word;
        } else {
          line = candidate;
        }
      }
      if (line) lines.push(line);

      return { ...node, label: lines.join("\n") };
    });
  }

  function getGraphMetrics(nodes) {
    const measure = measureTextContext();
    let maxRadius = 0;
    let maxLabelWidth = 0;
    let maxLabelHeight = 0;
    for (const node of nodes) {
      maxRadius = Math.max(maxRadius, node.size || 20);
      const font = getNodeFont(node, measure);
      const lines = String(node.label || "").split("\n");
      for (const line of lines) {
        maxLabelWidth = Math.max(maxLabelWidth, measure.measureText(line).width);
      }
      maxLabelHeight = Math.max(
        maxLabelHeight,
        lines.length * font.size * 1.2,
      );
    }
    return { maxRadius, maxLabelWidth, maxLabelHeight };
  }

  function getViewBounds() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    const allNodes = nodeData.get();
    const { maxRadius, maxLabelWidth, maxLabelHeight } =
      getGraphMetrics(allNodes);
    const padding = 6;
    const radius = Math.min(
      maxRadius,
      Math.max(0, (Math.min(width, height) - padding * 2) / 2),
    );
    const horizontalExtent = Math.max(radius, maxLabelWidth / 2);
    return {
      left: padding + horizontalExtent,
      right: width - padding - horizontalExtent,
      top: padding + radius,
      bottom: height - padding - radius - maxLabelHeight,
      width,
      height,
    };
  }

  function keepInside(nodeId, reflectVelocity) {
    const position = network.getPositions([nodeId])[nodeId];
    if (!position) return;
    const bounds = getViewBounds();
    const point = network.canvasToDOM(position);
    const next = {
      x: Math.max(bounds.left, Math.min(bounds.right, point.x)),
      y: Math.max(bounds.top, Math.min(bounds.bottom, point.y)),
    };
    if (next.x === point.x && next.y === point.y) return;

    const velocity = velocities.get(nodeId) || { x: 0, y: 0 };
    if (reflectVelocity) {
      if (point.x < bounds.left) velocity.x = Math.abs(velocity.x);
      if (point.x > bounds.right) velocity.x = -Math.abs(velocity.x);
      if (point.y < bounds.top) velocity.y = Math.abs(velocity.y);
      if (point.y > bounds.bottom) velocity.y = -Math.abs(velocity.y);
    }
    velocities.set(nodeId, velocity);
    const canvasPoint = network.DOMtoCanvas(next);
    network.moveNode(nodeId, canvasPoint.x, canvasPoint.y);
  }

  function pointerPosition(event) {
    const rect = host.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function beginNodeDrag(event) {
    if (!network || event.button !== 0) return;
    const pointer = pointerPosition(event);
    const nodeId = network.getNodeAt(pointer);
    if (nodeId === undefined) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    const canvasPosition = network.getPositions([nodeId])[nodeId];
    const center = network.canvasToDOM(canvasPosition);
    draggedNode = {
      id: nodeId,
      offsetX: center.x - pointer.x,
      offsetY: center.y - pointer.y,
    };
    host.setPointerCapture(event.pointerId);
  }

  function moveDraggedNode(event) {
    if (!network || !draggedNode) return;
    event.preventDefault();
    event.stopPropagation();
    const pointer = pointerPosition(event);
    const bounds = getViewBounds();
    const point = {
      x: Math.max(
        bounds.left,
        Math.min(bounds.right, pointer.x + draggedNode.offsetX),
      ),
      y: Math.max(
        bounds.top,
        Math.min(bounds.bottom, pointer.y + draggedNode.offsetY),
      ),
    };
    const canvasPoint = network.DOMtoCanvas(point);
    network.moveNode(draggedNode.id, canvasPoint.x, canvasPoint.y);
  }

  function finishNodeDrag(event) {
    if (!network || !draggedNode) return;
    event.preventDefault();
    event.stopPropagation();
    const nodeId = draggedNode.id;
    draggedNode = null;
    if (host.hasPointerCapture(event.pointerId)) {
      host.releasePointerCapture(event.pointerId);
    }

    const position = network.getPositions([nodeId])[nodeId];
    const point = network.canvasToDOM(position);
    const bounds = getViewBounds();
    const velocity = startingVelocity(nodeId);
    if (point.x <= bounds.left + 1) velocity.x = Math.abs(velocity.x);
    if (point.x >= bounds.right - 1) velocity.x = -Math.abs(velocity.x);
    if (point.y <= bounds.top + 1) velocity.y = Math.abs(velocity.y);
    if (point.y >= bounds.bottom - 1) velocity.y = -Math.abs(velocity.y);
    velocities.set(nodeId, velocity);
    network.selectNodes([nodeId]);
    setValue(nodeId);
  }

  function advanceAxis(position, velocity, elapsed, minimum, maximum) {
    const span = maximum - minimum;
    if (span <= 0) return { position: (minimum + maximum) / 2, velocity: 0 };

    const period = span * 2;
    const travel = position - minimum + velocity * elapsed;
    const phase = ((travel % period) + period) % period;
    if (phase <= span) {
      return { position: minimum + phase, velocity };
    }
    return { position: maximum - (phase - span), velocity: -velocity };
  }

  function applyGraphForces(nodes, positions, bounds, elapsed) {
    const accelerations = new Map(
      nodes.map((node) => [node.id, { x: 0, y: 0 }]),
    );
    const centerX = (bounds.left + bounds.right) / 2;
    const centerY = (bounds.top + bounds.bottom) / 2;

    for (let firstIndex = 0; firstIndex < nodes.length; firstIndex += 1) {
      const first = nodes[firstIndex];
      const firstPosition = positions.get(first.id);
      const firstAcceleration = accelerations.get(first.id);
      firstAcceleration.x += (centerX - firstPosition.x) * 0.015;
      firstAcceleration.y += (centerY - firstPosition.y) * 0.015;

      for (let secondIndex = firstIndex + 1; secondIndex < nodes.length; secondIndex += 1) {
        const second = nodes[secondIndex];
        const secondPosition = positions.get(second.id);
        const deltaX = firstPosition.x - secondPosition.x;
        const deltaY = firstPosition.y - secondPosition.y;
        const distanceSquared = deltaX * deltaX + deltaY * deltaY;
        if (distanceSquared < 1) continue;

        const distance = Math.sqrt(distanceSquared);
        const force = Math.min(120, 90_000 / distanceSquared);
        const forceX = (deltaX / distance) * force;
        const forceY = (deltaY / distance) * force;
        firstAcceleration.x += forceX;
        firstAcceleration.y += forceY;
        accelerations.get(second.id).x -= forceX;
        accelerations.get(second.id).y -= forceY;
      }
    }

    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    for (const edge of edgeData.get()) {
      const sourceId = edge.from || edge.source;
      const targetId = edge.to || edge.target;
      if (!nodeById.has(sourceId) || !nodeById.has(targetId)) continue;

      const sourcePosition = positions.get(sourceId);
      const targetPosition = positions.get(targetId);
      const deltaX = targetPosition.x - sourcePosition.x;
      const deltaY = targetPosition.y - sourcePosition.y;
      const distance = Math.hypot(deltaX, deltaY);
      if (distance < 1) continue;

      const spring = Math.max(-18, Math.min(18, (distance - 160) * 0.08));
      const forceX = (deltaX / distance) * spring;
      const forceY = (deltaY / distance) * spring;
      accelerations.get(sourceId).x += forceX;
      accelerations.get(sourceId).y += forceY;
      accelerations.get(targetId).x -= forceX;
      accelerations.get(targetId).y -= forceY;
    }

    const damping = Math.exp(-0.4 * elapsed);
    for (const node of nodes) {
      if (draggedNode && draggedNode.id === node.id) continue;
      const velocity = velocities.get(node.id) || startingVelocity(node.id);
      const acceleration = accelerations.get(node.id);
      velocity.x = (velocity.x + acceleration.x * elapsed) * damping;
      velocity.y = (velocity.y + acceleration.y * elapsed) * damping;
      velocities.set(node.id, velocity);
    }
  }

  function clampScale() {
    if (!network || !nodeData) return;
    const dimensions = getViewBounds();
    const maxNodeSize = nodeData.get().reduce(
      (largest, node) => Math.max(largest, node.size || 20),
      0,
    );
    const maxScale = Math.max(
      0.1,
      (Math.min(dimensions.width, dimensions.height) - 12) /
        (2 * maxNodeSize),
    );
    if (network.getScale() > maxScale) {
      network.moveTo({
        position: network.getViewPosition(),
        scale: maxScale,
        animation: false,
      });
    }
  }

  function animate(timestamp) {
    if (!network || !nodeData) return;
    const elapsed = lastFrameTime
      ? Math.min((timestamp - lastFrameTime) / 1000, 0.04)
      : 0;
    lastFrameTime = timestamp;
    const bounds = getViewBounds();
    const nodes = nodeData.get();
    const positions = new Map();
    for (const node of nodes) {
      const position = network.getPositions([node.id])[node.id];
      if (position) positions.set(node.id, network.canvasToDOM(position));
    }

    if (bounds.right >= bounds.left && bounds.bottom >= bounds.top) {
      applyGraphForces(nodes, positions, bounds, elapsed);
      for (const node of nodes) {
        if (draggedNode && draggedNode.id === node.id) continue;
        const point = positions.get(node.id);
        if (!point) continue;
        const velocity = velocities.get(node.id);
        const nextX = advanceAxis(
          point.x,
          velocity.x,
          elapsed,
          bounds.left,
          bounds.right,
        );
        const nextY = advanceAxis(
          point.y,
          velocity.y,
          elapsed,
          bounds.top,
          bounds.bottom,
        );
        velocity.x = nextX.velocity;
        velocity.y = nextY.velocity;
        velocities.set(node.id, velocity);
        const canvasPoint = network.DOMtoCanvas({
          x: nextX.position,
          y: nextY.position,
        });
        network.moveNode(node.id, canvasPoint.x, canvasPoint.y);
      }
    }

    animationFrame = window.requestAnimationFrame(animate);
  }

  function initialPositions(nodes, seed) {
    const { maxRadius, maxLabelWidth, maxLabelHeight } = getGraphMetrics(nodes);
    const padding = 6;
    const horizontalExtent = Math.max(maxRadius, maxLabelWidth / 2);
    const availableWidth = Math.max(1, host.clientWidth - 2 * (padding + horizontalExtent));
    const columnSpacing = Math.max(2 * maxRadius + 30, maxLabelWidth + 30);
    const columns = Math.max(
      1,
      Math.min(nodes.length || 1, Math.floor(availableWidth / columnSpacing)),
    );
    const rows = Math.max(1, Math.ceil(nodes.length / columns));
    const horizontalSpacing = Math.max(columnSpacing, availableWidth / columns);
    const verticalSpacing = Math.max(
      130,
      2 * maxRadius + maxLabelHeight + 30,
    );
    let randomState = (seed >>> 0) || 1;
    const random = () => {
      randomState = (Math.imul(1664525, randomState) + 1013904223) >>> 0;
      return randomState / 4294967296;
    };
    return nodes.map((node, index) => ({
      ...node,
      x:
        (index % columns - (columns - 1) / 2) * horizontalSpacing +
        (random() - 0.5) * 30,
      y:
        (Math.floor(index / columns) - (rows - 1) / 2) * verticalSpacing +
        (random() - 0.5) * 30,
      physics: false,
    }));
  }

  function mountGraph(payload) {
    if (!window.vis || !window.vis.Network) {
      loadError.hidden = false;
      return;
    }
    loadError.hidden = true;

    const graph = payload.graph || { nodes: [], edges: [] };
    const graphJson = JSON.stringify(graph);
    if (network && graphJson === renderedGraph) return;

    if (network) {
      network.destroy();
      network = null;
    }
    if (animationFrame !== null) {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }
    velocities.clear();
    renderedGraph = graphJson;
    const config = payload.config || {};

    sourceNodes = graph.nodes || [];
    const nodes = initialPositions(
      fitNodeLabels(sourceNodes, host.clientWidth),
      config.layout?.randomSeed || 1,
    );
    const edges = graph.edges || [];
    nodeData = new window.vis.DataSet(nodes);
    edgeData = new window.vis.DataSet(edges);
    const options = {
      ...config,
      autoResize: true,
      physics: { enabled: false },
      layout: { ...(config.layout || {}), improvedLayout: false },
      interaction: {
        dragNodes: false,
        zoomView: true,
        dragView: true,
        ...(config.interaction || {}),
      },
    };

    network = new window.vis.Network(
      host,
      { nodes: nodeData, edges: edgeData },
      options,
    );
    if (nodes.length) {
      network.fit({ nodes: nodes.map((node) => node.id), animation: false });
      clampScale();
    }

    network.on("selectNode", (event) => setValue(event.nodes[0] || null));
    network.on("deselectNode", () => setValue(null));
    network.on("click", (event) => {
      if (!event.nodes || event.nodes.length === 0) {
        network.unselectAll();
        setValue(null);
      }
    });
    network.on("zoom", clampScale);

    if (selectedNode && nodes.some((node) => node.id === selectedNode)) {
      network.selectNodes([selectedNode]);
    } else if (selectedNode) {
      setValue(null);
    }

    for (const node of nodes) {
      velocities.set(node.id, startingVelocity(node.id));
    }
    lastFrameTime = 0;
    animationFrame = window.requestAnimationFrame(animate);
  }

  host.addEventListener("pointerdown", beginNodeDrag, true);
  host.addEventListener("pointermove", moveDraggedNode, true);
  host.addEventListener("pointerup", finishNodeDrag, true);
  host.addEventListener("pointercancel", finishNodeDrag, true);

  window.addEventListener("message", (event) => {
    const message = event.data;
    if (message && message.type === "streamlit:render") {
      mountGraph(message.args.payload || {});
    }
  });

  const resizeObserver = new ResizeObserver(() => {
    if (!network || !nodeData) return;
    const updatedLabels = fitNodeLabels(sourceNodes, host.clientWidth);
    nodeData.update(
      updatedLabels.map((node) => ({ id: node.id, label: node.label })),
    );
    clampScale();
    for (const node of nodeData.get()) keepInside(node.id, true);
  });
  resizeObserver.observe(frame);

  window.addEventListener("error", (event) => {
    if (event.filename && event.filename.includes("vis-network")) {
      loadError.hidden = false;
    }
  });

  postMessage("streamlit:componentReady", { apiVersion: 1 });
  postMessage("streamlit:setFrameHeight", { height: 540 });
})();
