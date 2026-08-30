import unittest
from engine import evaluate_scene, counterfactual_effects

class CausalRealityEngineTests(unittest.TestCase):
    def test_rejects_orphan_visible_effect(self):
        scene = {"nodes":[{"id":"smudge","kind":"effect","visible":True}],"edges":[]}
        result = evaluate_scene(scene)
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("orphan_effect:smudge", result["findings"])

    def test_rejects_causal_cycle(self):
        scene = {"nodes":[{"id":"a","kind":"cause"},{"id":"b","kind":"effect","visible":True}],"edges":[["a","b"],["b","a"]]}
        result = evaluate_scene(scene)
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("causal_cycle", result["findings"])

    def test_counterfactual_propagates_downstream(self):
        scene = {"nodes":[{"id":"heat","kind":"cause"},{"id":"sweat","kind":"transition"},{"id":"shine","kind":"effect","visible":True}],"edges":[["heat","sweat"],["sweat","shine"]]}
        self.assertEqual(counterfactual_effects(scene, "heat"), ["shine", "sweat"])

    def test_imperfection_budget_rejects_sterile_and_theatrical(self):
        sterile = {"nodes":[{"id":"a","kind":"cause"},{"id":"b","kind":"effect","visible":True}],"edges":[["a","b"]],"imperfections":0,"opportunities":10}
        theatrical = {**sterile,"imperfections":9}
        self.assertIn("imperfection_budget:sterile", evaluate_scene(sterile)["findings"])
        self.assertIn("imperfection_budget:theatrical", evaluate_scene(theatrical)["findings"])

    def test_receipt_has_no_effect_authority(self):
        scene = {"nodes":[{"id":"a","kind":"cause"},{"id":"b","kind":"effect","visible":True}],"edges":[["a","b"]],"imperfections":2,"opportunities":10}
        result = evaluate_scene(scene)
        self.assertEqual(result["authority"], "none")
        self.assertEqual(result["effect_authority"], "none")

if __name__ == "__main__": unittest.main()
