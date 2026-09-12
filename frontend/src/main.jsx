import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "antd/dist/reset.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";
import "./styles/brand.css";
import App from "./App.jsx";
import { configureMapLibreWorker } from "./config/mapLibreWorker.js";

// 建立任何地圖前，先設定 MapLibre 6 的 worker URL（Vite bundler 必要步驟）。
configureMapLibreWorker();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
