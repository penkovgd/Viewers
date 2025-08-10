import React from 'react';
import { useSystem } from '@ohif/core';

export default function CurvedMprSidePanelComponent() {
  const { commandsManager } = useSystem();

  const handleClick = () => {
    commandsManager.runCommand('sendMeasurments', {});
  };

  return (
    <div className="text-white">
      <p>Curved MPR</p>
      <button className="btn border-2 border-solid border-white" onClick={handleClick}>
        Send Measurements
      </button>
    </div>
  );
}
