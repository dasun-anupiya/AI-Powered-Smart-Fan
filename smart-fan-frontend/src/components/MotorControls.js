import React from "react";
import "./MotorControls.css";

const MotorControls = ({
  espIp,
  setEspIp,
  onDcOn,
  dcLoading,
  onStepperLeftDown,
  onStepperLeftUp,
  onStepperRightDown,
  onStepperRightUp,
}) => (
  <div className="motor-controls">
    <input
      type="text"
      placeholder="ESP32 IP (e.g. 192.168.1.100)"
      value={espIp}
      onChange={(e) => setEspIp(e.target.value)}
      style={{ width: "80%" }}
    />
    <button onClick={onDcOn} disabled={dcLoading}>
      {dcLoading ? "Turning ON..." : "DC Motor ON"}
    </button>
    <div className="stepper-buttons">
      <button
        onMouseDown={onStepperLeftDown}
        onMouseUp={onStepperLeftUp}
        onTouchStart={onStepperLeftDown}
        onTouchEnd={onStepperLeftUp}
      >
        ◀️ Left
      </button>
      <button
        onMouseDown={onStepperRightDown}
        onMouseUp={onStepperRightUp}
        onTouchStart={onStepperRightDown}
        onTouchEnd={onStepperRightUp}
      >
        Right ▶️
      </button>
    </div>
  </div>
);

export default MotorControls; 