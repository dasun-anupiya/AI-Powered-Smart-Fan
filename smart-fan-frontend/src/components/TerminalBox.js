import React from "react";
import "./TerminalBox.css";

const TerminalBox = ({ data }) => (
  <div className="terminal-box">
    <pre>{data}</pre>
  </div>
);

export default TerminalBox; 