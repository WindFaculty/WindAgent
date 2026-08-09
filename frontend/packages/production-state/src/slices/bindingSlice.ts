import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  ProductionAssetBindingDTO,
  AssetRequirementDTO,
  AssetEligibilityResultDTO,
} from '@windagent/production-contracts';

export interface BindingState {
  bindings: ProductionAssetBindingDTO[];
  requirements: AssetRequirementDTO[];
  eligibilityMap: Record<string, AssetEligibilityResultDTO>;
  activeResolverRequirementId: string | null;
  activePickerEntityId: string | null;
  loading: boolean;
  error: string | null;
}

const initialState: BindingState = {
  bindings: [
    {
      binding_id: 'bnd_bunny_01',
      project_id: 'vp_01',
      production_revision_id: 'rev_13',
      screenplay_entity_type: 'CHARACTER',
      screenplay_entity_id: 'char_bunny',
      role_key: 'primary',
      asset_id: 'asset_bunny',
      asset_revision_id: 'rev_asset_bunny_v1',
      status: 'ACTIVE',
      created_by: 'user',
      created_at: new Date().toISOString(),
    },
    {
      binding_id: 'bnd_park_01',
      project_id: 'vp_01',
      production_revision_id: 'rev_13',
      screenplay_entity_type: 'LOCATION',
      screenplay_entity_id: 'loc_park',
      role_key: 'primary',
      asset_id: 'asset_park',
      asset_revision_id: 'rev_asset_park_v1',
      status: 'ACTIVE',
      created_by: 'user',
      created_at: new Date().toISOString(),
    },
  ],
  requirements: [
    {
      requirement_id: 'req_ball_01',
      project_id: 'vp_01',
      revision_id: 'rev_13',
      screenplay_entity_id: 'prop_ball',
      screenplay_entity_type: 'PROP',
      role_key: 'primary',
      required_kind: 'PROP_3D_OBJECT',
      required_media: 'IMAGE',
      description: "Missing 3D prop asset for 'Red Beach Ball'",
      severity: 'BLOCKING',
      status: 'OPEN',
      candidate_asset_ids: [],
    },
  ],
  eligibilityMap: {},
  activeResolverRequirementId: null,
  activePickerEntityId: null,
  loading: false,
  error: null,
};

export const bindingSlice = createSlice({
  name: 'binding',
  initialState,
  reducers: {
    setBindings(state, action: PayloadAction<ProductionAssetBindingDTO[]>) {
      state.bindings = action.payload;
    },
    addBinding(state, action: PayloadAction<ProductionAssetBindingDTO>) {
      state.bindings = state.bindings.filter((b) => b.binding_id !== action.payload.binding_id);
      state.bindings.push(action.payload);
      // Close requirement if fulfilled
      state.requirements = state.requirements.map((req) =>
        req.screenplay_entity_id === action.payload.screenplay_entity_id
          ? { ...req, status: 'FULFILLED' }
          : req
      );
    },
    removeBinding(state, action: PayloadAction<string>) {
      state.bindings = state.bindings.filter((b) => b.binding_id !== action.payload);
    },
    setRequirements(state, action: PayloadAction<AssetRequirementDTO[]>) {
      state.requirements = action.payload;
    },
    updateRequirementStatus(
      state,
      action: PayloadAction<{ requirementId: string; status: AssetRequirementDTO['status'] }>
    ) {
      const req = state.requirements.find((r) => r.requirement_id === action.payload.requirementId);
      if (req) {
        req.status = action.payload.status;
      }
    },
    setEligibility(state, action: PayloadAction<AssetEligibilityResultDTO>) {
      state.eligibilityMap[action.payload.asset_id] = action.payload;
    },
    openResolver(state, action: PayloadAction<string>) {
      state.activeResolverRequirementId = action.payload;
    },
    closeResolver(state) {
      state.activeResolverRequirementId = null;
    },
    openPicker(state, action: PayloadAction<string>) {
      state.activePickerEntityId = action.payload;
    },
    closePicker(state) {
      state.activePickerEntityId = null;
    },
  },
});

export const {
  setBindings,
  addBinding,
  removeBinding,
  setRequirements,
  updateRequirementStatus,
  setEligibility,
  openResolver,
  closeResolver,
  openPicker,
  closePicker,
} = bindingSlice.actions;

export default bindingSlice.reducer;
