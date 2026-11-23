// Test-only entry: render the production component over the real native bridge.
import React from "react";
import { createRoot } from "react-dom/client";
import { CustomerHistoryModal } from "../src/components/CustomerHistoryModal";
import "../src/index.css";
const params = new URLSearchParams(window.location.hash.slice(1));
createRoot(document.getElementById("root")!).render(
  <CustomerHistoryModal phone={params.get("phone") || undefined}
    customerId={params.has("customerId") ? Number(params.get("customerId")) : undefined}
    onClose={() => {}} />
);
