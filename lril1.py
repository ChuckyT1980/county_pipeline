from dataclasses import dataclass
from typing import Optional

@dataclass
class InferredRegimeState:
    regime_label: str
    gradient_dt: float
    confidence: float
    is_transitioning: bool

class LatentRegimeInferenceLayer:
    """
    LRIL-1: Latent Regime Inference Layer.
    Hierarchical inference engine:
      - Primary: CARS-2 velocity field (EMA gradient)
      - Secondary: CVA-1 categorical jumps (catalyst)
    """
    def __init__(self, velocity_threshold: float = 0.10):
        self.velocity_threshold = velocity_threshold
        
        self.prev_vsi: Optional[float] = None
        self.prev_fme: Optional[float] = None
        self.prev_cva_class: Optional[str] = None
        
        self.smoothed_dvsi: float = 0.0
        self.smoothed_dfme: float = 0.0
        
        self.current_regime: str = "INITIALIZING"
        self.confidence: float = 0.0
        
    def infer(self, current_vsi: float, current_fme: float, current_cva_class: str) -> InferredRegimeState:
        if self.prev_vsi is None:
            # First tick initialization
            self.prev_vsi = current_vsi
            self.prev_fme = current_fme
            self.prev_cva_class = current_cva_class
            self.current_regime = current_cva_class # Baseline assumption
            self.confidence = 0.5
            return InferredRegimeState(self.current_regime, 0.0, self.confidence, False)
            
        # 1. Compute Continuous Velocity (Smoothed to reject single-step noise)
        raw_dvsi = abs(current_vsi - self.prev_vsi)
        raw_dfme = abs(current_fme - self.prev_fme)
        
        self.smoothed_dvsi = (0.2 * raw_dvsi) + (0.8 * self.smoothed_dvsi)
        self.smoothed_dfme = (0.2 * raw_dfme) + (0.8 * self.smoothed_dfme)
        
        gradient_dt = max(self.smoothed_dvsi, self.smoothed_dfme)
        
        # 2. Check Categorical Jump (Secondary Signal)
        cva_jumped = (current_cva_class != self.prev_cva_class)
        
        is_transitioning = False
        
        # 3. Hierarchical Inference Rule
        if gradient_dt < self.velocity_threshold:
            # Velocity is low. We are in a stable field.
            if cva_jumped:
                # CVA-1 jumped but field didn't move enough -> Treat as NOISE. Ignore label.
                # Confidence drops slightly due to contradiction, but regime holds.
                self.confidence = max(0.1, self.confidence - 0.2)
                # DO NOT update prev_cva_class to preserve the real boundary
                self.prev_vsi = current_vsi
                self.prev_fme = current_fme
                return InferredRegimeState(self.current_regime, gradient_dt, self.confidence, False)
            else:
                # Stable field, stable observation -> Build confidence.
                self.confidence = min(1.0, self.confidence + 0.3)
                if self.confidence >= 0.7 and self.current_regime == "AMBIGUOUS":
                    self.current_regime = current_cva_class
        else:
            # Velocity is high. We are crossing a boundary.
            is_transitioning = True
            self.confidence = max(0.1, self.confidence - 0.3) # Epistemic shock
            
            if cva_jumped:
                # CVA-1 jump confirms the high gradient. Catalyst triggers regime change.
                self.current_regime = current_cva_class
                self.confidence += 0.4 # Catalyst accelerates confidence in new regime
            elif self.current_regime == current_cva_class:
                # We already aligned with the label. High gradient is just EMA tail settling.
                self.confidence = max(0.1, self.confidence - 0.1)
            else:
                # High gradient but no categorical jump yet -> Hidden drift detected.
                self.current_regime = "AMBIGUOUS"
                
        # 4. State Update
        self.prev_vsi = current_vsi
        self.prev_fme = current_fme
        self.prev_cva_class = current_cva_class
        
        return InferredRegimeState(self.current_regime, gradient_dt, self.confidence, is_transitioning)
