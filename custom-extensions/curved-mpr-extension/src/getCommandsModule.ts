import { utils } from '@ohif/core';

export default function getCommandsModule({ servicesManager, commandsManager, extensionManager }) {
  const { measurementService } = servicesManager.services;
  const actions = {
    sendMeasurments: async () => {
      const { filterTool } = utils.MeasurementFilters;
      const measurementData = measurementService.getMeasurements(filterTool('Probe'));
      console.log('Got measurments:', measurementData);
      if (measurementData.length < 2) {
        // throw new Error('At least 2 points required');
        console.error('At least 2 points required');
        return;
      }
      try {
        const response = await fetch('https://httpbin.org/post', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ measurements: measurementData }),
        });

        if (!response.ok) {
          throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        console.log('Server response:', result);
      } catch (err) {
        console.error('Falied to send measurements:', err);
      }
    },
  };
  const definitions = {
    sendMeasurments: {
      commandFn: actions.sendMeasurments,
    },
  };
  return {
    actions,
    definitions,
    defaultContext: 'ROUTE:VIEWER',
  };
}
