from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile

class DashboardAggregator:
    """
    EXPLICITLY NON-ROUTING, NON-EXECUTION, OBSERVATIONAL ONLY.
    DO NOT FEED THESE SCORES BACK INTO THE SYSTEM.
    """
    @staticmethod
    def generate_scalar_cars(eval_vector: EvaluationVector, profile: VendorHealthProfile) -> float:
        # Scalar generation for dashboard (0.30 * EFS) + (0.25 * VSI) + (0.25 * SER) + (0.20 * (1 - FME))
        # Note: We use the EMA from the state profile for VSI and FME to get the smoothed "health".
        efs = eval_vector.efs
        ser = eval_vector.ser
        vsi = profile.ema_vsi
        fme = profile.ema_fme
        
        cars_score = (0.30 * efs) + (0.25 * vsi) + (0.25 * ser) + (0.20 * (1.0 - fme))
        return round(cars_score, 3)

    @staticmethod
    def print_dashboard(eval_vector: EvaluationVector, profile: VendorHealthProfile):
        score = DashboardAggregator.generate_scalar_cars(eval_vector, profile)
        print("="*50)
        print("  CARS-2 VENDOR HEALTH DASHBOARD (OBSERVATIONAL)")
        print("="*50)
        print(f"Vendor Class:       {profile.vendor_class}")
        print(f"Total Executions:   {profile.total_executions}")
        print("-" * 50)
        print(f"Atomic EFS:         {eval_vector.efs:.2f} (Execution Fidelity)")
        print(f"Atomic SER:         {eval_vector.ser:.2f} (Strategy Efficiency)")
        print(f"Stateful EMA VSI:   {profile.ema_vsi:.2f} (Vendor Stability)")
        print(f"Stateful EMA FME:   {profile.ema_fme:.2f} (Failure Mode Entropy)")
        print("-" * 50)
        print(f"CARS Score (Scalar): {score:.3f}")
        print("="*50)
