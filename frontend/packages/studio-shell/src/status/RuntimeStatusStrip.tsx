import React from 'react';
import { BackendStatus, BackendStatusProps } from './BackendStatus';
import { RuntimeMetrics, RuntimeMetricsProps } from './RuntimeMetrics';

export interface RuntimeStatusStripProps extends BackendStatusProps, RuntimeMetricsProps {}

export const RuntimeStatusStrip: React.FC<RuntimeStatusStripProps> = ({
  backendOnline,
  hermesOnline,
  metrics,
}) => {
  return (
    <>
      <BackendStatus backendOnline={backendOnline} hermesOnline={hermesOnline} />
      <RuntimeMetrics metrics={metrics} />
    </>
  );
};

export default RuntimeStatusStrip;
