import React, { useState, useEffect, useRef } from "react";
import TerminalBox from "./components/TerminalBox";
import MotorControls from "./components/MotorControls";
import "./App.css";

function App() {
  const [espIp, setEspIp] = useState("");
  const [terminalData, setTerminalData] = useState("Waiting for data...");
  const [dcLoading, setDcLoading] = useState(false);

  // Fetch coordinates from Flask server every second
  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/coordinates")
        .then((res) => res.json())
        .then((data) => setTerminalData(JSON.stringify(data, null, 2)))
        .catch(() => setTerminalData("Error fetching data"));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Send command to ESP32
  const sendEspCommand = async (cmd) => {
    if (!espIp) {
      alert("Please enter ESP32 IP");
      return;
    }
    try {
      await fetch(`http://${espIp}/motor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
    } catch (e) {
      alert("Failed to send command to ESP32");
    }
  };

  // DC Motor ON
  const handleDcOn = () => {
    setDcLoading(true);
    sendEspCommand("dc_on").finally(() => setDcLoading(false));
  };

  // Stepper Motor Controls
  const handleStepper = (dir) => {
    sendEspCommand(dir === "left" ? "stepper_left" : "stepper_right");
  };

  const handleStepperStop = () => {
    sendEspCommand("stop");
  };

  return (
    <div className="App">
      <h2>Smart Fan Control</h2>
      <MotorControls
        espIp={espIp}
        setEspIp={setEspIp}
        onDcOn={handleDcOn}
        dcLoading={dcLoading}
        onStepperLeftDown={() => handleStepper("left")}
        onStepperLeftUp={handleStepperStop}
        onStepperRightDown={() => handleStepper("right")}
        onStepperRightUp={handleStepperStop}
      />
      <TerminalBox data={terminalData} />
    </div>
  );
}

export default App;
