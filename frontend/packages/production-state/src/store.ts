import { configureStore } from '@reduxjs/toolkit';
import { projectContextSlice } from './slices/projectContextSlice';
import { screenplaySlice } from './slices/screenplaySlice';
import { bindingSlice } from './slices/bindingSlice';
import { recoverySlice } from './slices/recoverySlice';

export function createProductionStore() {
  return configureStore({
    reducer: {
      projectContext: projectContextSlice.reducer,
      screenplay: screenplaySlice.reducer,
      binding: bindingSlice.reducer,
      recovery: recoverySlice.reducer,
    },
  });
}

export type ProductionStore = ReturnType<typeof createProductionStore>;
export type ProductionRootState = ReturnType<ProductionStore['getState']>;
export type ProductionAppDispatch = ProductionStore['dispatch'];
