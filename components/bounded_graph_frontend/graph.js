(() => {
  const frame = document.getElementById("graph-frame");
  const host = document.getElementById("network");
  const loadError = document.getElementById("load-error");
  const velocities = new Map();
  let network = null;
  let nodeData = null;
  let edgeData = null;
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

  function getViewBounds() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    const allNodes = nodeData.get();
    const maxRadius = allNodes.reduce(
      (largest, node) => Math.max(largest, node.size || 20),
      0,
    );
    const padding = 6;
    const radius = Math.min(
      maxRadius,
      Math.max(0, (Math.min(width, height) - padding * 2) / 2),
    );
    return {
      left: padding + radius,
      right: width - padding - radius,
      top: padding + radius,
      bottom: height - padding - radius,
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

    if (bounds.right >= bounds.left && bounds.bottom >= bounds.top) {
      for (const node of nodeData.get()) {
        const position = network.getPositions([node.id])[node.id];
        if (!position) continue;
        const point = network.canvasToDOM(position);
        const velocity = velocities.get(node.id) || startingVelocity(node.id);
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
    const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
    const rows = Math.max(1, Math.ceil(nodes.length / columns));
    const spacing = 105;
    let randomState = (seed >>> 0) || 1;
    const random = () => {
      randomState = (Math.imul(1664525, randomState) + 1013904223) >>> 0;
      return randomState / 4294967296;
    };
    return nodes.map((node, index) => ({
      ...node,
      x:
        (index % columns - (columns - 1) / 2) * spacing +
        (random() - 0.5) * 30,
      y:
        (Math.floor(index / columns) - (rows - 1) / 2) * spacing +
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

    const nodes = initialPositions(
      graph.nodes || [],
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
    network.on("zoom", clampScale);

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
