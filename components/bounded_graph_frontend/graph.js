(() => {
  const frame = document.getElementById("graph-frame");
  const host = document.getElementById("network");
  const loadError = document.getElementById("load-error");
  let network = null;
  let nodes = null;
  let edges = null;
  let sourceNodes = [];
  let sourceEdges = [];
  let selected = null;
  let topology = "";
  let scale = 1;
  let settling = false;

  function post(type, data = {}) {
    window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, "*");
  }
  function select(id) {
    if (selected === id) return;
    selected = id;
    post("streamlit:setComponentValue", { value: id });
  }
  function adjacent(id) {
    const result = new Set([id]);
    for (const edge of sourceEdges) {
      const from = edge.from ?? edge.source;
      const to = edge.to ?? edge.target;
      if (from === id) result.add(to);
      if (to === id) result.add(from);
    }
    return result;
  }
  function paint(focus = selected) {
    const neighbors = focus ? adjacent(focus) : null;
    const degrees = new Map();
    for (const edge of sourceEdges) {
      for (const id of [edge.from ?? edge.source, edge.to ?? edge.target]) {
        degrees.set(id, (degrees.get(id) || 0) + 1);
      }
    }
    nodes.update(sourceNodes.map(node => {
      const dim = neighbors && !neighbors.has(node.id);
      const base = typeof node.color === "string" ? node.color : "#64748b";
      return {
        id: node.id, label: node.label, shape: "dot",
        size: (6 + Math.min(5, Math.log2(1 + (degrees.get(node.id) || 0)) * 1.6)) * scale,
        borderWidth: 0,
        color: {
          background: dim ? "#dce1e9" : base,
          border: base,
          highlight: { background: "#2166db", border: "#2166db" },
          hover: { background: "#2166db", border: "#2166db" },
        },
        font: { face: "Arial", size: 14 * scale, color: dim ? "#c3c9d2" : "#243047", strokeWidth: 3, strokeColor: "#ffffff" },
      };
    }));
    edges.update(sourceEdges.map((edge, index) => {
      const from = edge.from ?? edge.source;
      const to = edge.to ?? edge.target;
      const active = focus && (from === focus || to === focus);
      return {
        id: `edge-${index}`, from, to,
        label: "", title: edge.label || "Related",
        width: active ? 1.4 : 0.65,
        color: { color: active ? "#7a9bcc" : (focus ? "#edf0f4" : "#d3d8df"), highlight: "#7a9bcc", hover: "#7a9bcc", inherit: false },
        arrows: { from: { enabled: false }, to: { enabled: false } },
        dashes: false, smooth: false,
      };
    }));
  }
  function fit() {
    if (network && sourceNodes.length) network.fit({ animation: false, padding: 45 });
  }
  function mount(payload) {
    if (!window.vis?.Network) {
      loadError.hidden = false;
      return;
    }
    loadError.hidden = true;
    const graph = payload.graph || { nodes: [], edges: [] };
    const config = payload.config || {};
    scale = Math.max(.55, Math.min(1.6, Number(payload.nodeScale) || 1));
    sourceNodes = graph.nodes || [];
    sourceEdges = graph.edges || [];
    const requestedFocus = config.focusTopic ?? null;
    selected = sourceNodes.some(node => node.id === requestedFocus) ? requestedFocus : null;
    const nextTopology = JSON.stringify({
      nodes: sourceNodes.map(node => [node.id, node.label]),
      edges: sourceEdges.map(edge => [edge.from ?? edge.source, edge.to ?? edge.target, edge.label]),
      seed: config.layout?.randomSeed || 42,
    });
    if (network && nextTopology === topology) {
      paint();
      if (selected) network.selectNodes([selected]);
      else network.unselectAll();
      return;
    }
    topology = nextTopology;
    if (network) network.destroy();
    nodes = new window.vis.DataSet(sourceNodes.map(node => ({ id: node.id })));
    edges = new window.vis.DataSet([]);
    paint();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    network = new window.vis.Network(host, { nodes, edges }, {
      autoResize: true,
      layout: { randomSeed: config.layout?.randomSeed || 42, improvedLayout: true },
      physics: {
        enabled: !reducedMotion, solver: "barnesHut", minVelocity: .18, maxVelocity: 12,
        barnesHut: { gravitationalConstant: -4500, centralGravity: .12, springLength: 150, springConstant: .025, damping: .35, avoidOverlap: .5 },
        stabilization: { enabled: false },
      },
      interaction: { dragNodes: true, dragView: true, zoomView: true, hover: true, tooltipDelay: 250, hideEdgesOnDrag: false },
      nodes: { shape: "dot", chosen: true },
      edges: { selectionWidth: 1, hoverWidth: 1 },
    });
    settling = !reducedMotion;
    network.once("afterDrawing", fit);
    const finishSettling = () => {
      if (!settling) return;
      settling = false;
      fit();
    };
    network.once("stabilizationIterationsDone", finishSettling);
    network.once("stabilized", finishSettling);
    network.on("click", event => {
      select(event.nodes?.[0] ?? null);
      paint();
    });
    network.on("hoverNode", event => paint(event.node));
    network.on("blurNode", () => paint());
    network.on("dragStart", () => {
      // Keep the camera still while the user explores the elastic network.
      settling = false;
    });
    network.on("dragEnd", () => {
      if (!reducedMotion) network.startSimulation();
    });
    if (selected && sourceNodes.some(node => node.id === selected)) {
      network.selectNodes([selected]);
    } else if (selected !== null) {
      select(null);
    }
  }
  window.addEventListener("message", event => {
    if (event.data?.type === "streamlit:render") mount(event.data.args.payload || {});
  });
  new ResizeObserver(() => { if (!settling) fit(); }).observe(frame);
  window.addEventListener("error", event => {
    if (event.filename?.includes("vis-network")) loadError.hidden = false;
  });
  post("streamlit:componentReady", { apiVersion: 1 });
  post("streamlit:setFrameHeight", { height: 540 });
})();
