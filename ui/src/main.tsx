import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource/inter";
import { PorscheDesignSystemProvider } from "@porsche-design-system/components-react";
import { App } from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PorscheDesignSystemProvider>
      <App />
    </PorscheDesignSystemProvider>
  </React.StrictMode>,
);
