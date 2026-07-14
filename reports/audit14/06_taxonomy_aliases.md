# Taxonomy Aliases

{
  "taxonomy_path": "C:\\Study\\SuperRAGSystem\\acne-agent-system\\data\\taxonomy\\drug_aliases.yaml",
  "taxonomy_version": "drug_taxonomy_v1",
  "alias_count": 68,
  "coverage": {
    "Tazorac": {
      "alias_present": false,
      "resolved_canonical_names": []
    },
    "Differin": {
      "alias_present": true,
      "resolved_canonical_names": [
        "Differin"
      ]
    },
    "Epiduo": {
      "alias_present": true,
      "resolved_canonical_names": [
        "Epiduo"
      ]
    },
    "tazarotene": {
      "alias_present": false,
      "resolved_canonical_names": []
    },
    "adapalene": {
      "alias_present": true,
      "resolved_canonical_names": [
        "adapalene"
      ]
    },
    "benzoyl_peroxide": {
      "alias_present": true,
      "resolved_canonical_names": [
        "benzoyl_peroxide"
      ]
    },
    "tretinoin": {
      "alias_present": true,
      "resolved_canonical_names": [
        "tretinoin"
      ]
    },
    "isotretinoin": {
      "alias_present": true,
      "resolved_canonical_names": [
        "isotretinoin"
      ]
    },
    "clindamycin": {
      "alias_present": true,
      "resolved_canonical_names": [
        "clindamycin"
      ]
    },
    "erythromycin": {
      "alias_present": false,
      "resolved_canonical_names": []
    },
    "salicylic_acid": {
      "alias_present": false,
      "resolved_canonical_names": []
    },
    "azelaic_acid": {
      "alias_present": true,
      "resolved_canonical_names": [
        "azelaic_acid"
      ]
    },
    "topical_retinoid": {
      "alias_present": true,
      "resolved_canonical_names": [
        "topical_retinoid"
      ]
    },
    "topical_antibiotic": {
      "alias_present": true,
      "resolved_canonical_names": [
        "topical_antibiotic"
      ]
    },
    "pregnancy": {
      "alias_present": true,
      "resolved_canonical_names": [
        "pregnancy"
      ]
    },
    "breastfeeding": {
      "alias_present": true,
      "resolved_canonical_names": [
        "breastfeeding"
      ]
    },
    "severe_acne": {
      "alias_present": true,
      "resolved_canonical_names": [
        "severe_acne"
      ]
    },
    "acne_vulgaris": {
      "alias_present": true,
      "resolved_canonical_names": [
        "acne_vulgaris"
      ]
    }
  },
  "tazorac_case_expansion": {
    "expanded_terms": [
      "Differin",
      "diferin",
      "Epiduo",
      "epiduo gel",
      "adapalene",
      "adapalen",
      "topical_retinoid",
      "retinoid bôi",
      "retinoid",
      "benzoyl_peroxide",
      "benzoyl peroxid",
      "bpo",
      "bp"
    ],
    "normalized_entities": [
      {
        "canonical_name": "Differin",
        "entity_type": "drug_product",
        "active_ingredients": [
          "adapalene"
        ],
        "drug_class": [
          "topical_retinoid"
        ]
      },
      {
        "canonical_name": "Epiduo",
        "entity_type": "drug_product",
        "active_ingredients": [
          "adapalene",
          "benzoyl_peroxide"
        ],
        "drug_class": [
          "topical_retinoid",
          "benzoyl_peroxide"
        ]
      },
      {
        "canonical_name": "adapalene",
        "entity_type": "active_ingredient",
        "active_ingredients": [],
        "drug_class": [
          "topical_retinoid"
        ]
      },
      {
        "canonical_name": "topical_retinoid",
        "entity_type": "drug_class",
        "active_ingredients": [],
        "drug_class": []
      },
      {
        "canonical_name": "benzoyl_peroxide",
        "entity_type": "active_ingredient",
        "active_ingredients": [],
        "drug_class": [
          "benzoyl_peroxide"
        ]
      },
      {
        "canonical_name": "benzoyl_peroxide",
        "entity_type": "drug_class",
        "active_ingredients": [],
        "drug_class": []
      }
    ]
  }
}
