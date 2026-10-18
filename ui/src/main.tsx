import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource/inter";
import { PorscheDesignSystemProvider } from "@porsche-design-system/components-react";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles.css";

const currentPath = window.location.pathname;
let basename = "/";
if (currentPath.startsWith("/ms/bidding")) {
  basename = "/ms/bidding";
} else if (currentPath.startsWith("/ms/tender-bidding")) {
  basename = "/ms/tender-bidding";
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PorscheDesignSystemProvider>
      <BrowserRouter basename={basename}>
        <App />
      </BrowserRouter>
    </PorscheDesignSystemProvider>
  </React.StrictMode>,
);
