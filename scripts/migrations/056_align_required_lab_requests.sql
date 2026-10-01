-- Migration 056: align the authored request rail with the current lab guide.
-- Build/proof commands are separate guide steps, not extra conversation turns.
-- Update only known authored rows; preserve participant-authored variations.
\set ON_ERROR_STOP on

BEGIN;

UPDATE pellier.workshop_scenarios
   SET journey_role = 'explore', journey_stage = NULL
 WHERE persona_id = 'marco' AND ordinal = 2 AND journey_role = 'required'
   AND prompt = 'What would go with the Hadley Linen Shirt?';

UPDATE pellier.workshop_scenarios
   SET journey_role = 'explore', journey_stage = NULL
 WHERE persona_id = 'anna' AND journey_role = 'required'
   AND ((ordinal = 2 AND prompt = 'Keep it under $100 and in stock. Show me the strongest two options.')
     OR (ordinal = 3 AND prompt = 'Which one should I choose? Compare the two options using their current prices and availability.'));

UPDATE pellier.workshop_scenarios
   SET journey_role = 'explore', journey_stage = NULL
 WHERE persona_id = 'theo' AND ordinal = 2 AND journey_role = 'required'
   AND prompt = 'What goes well with the pour-over set, keeping to the same materials and morning routine?';

UPDATE pellier.workshop_scenarios
   SET prompt = 'Show my support ticket history, and the history for customer CUST-JESSICA.',
       journey_stage = 'exercise', preview_product_id = NULL
 WHERE persona_id = 'theo' AND ordinal = 3 AND journey_role = 'required'
   AND prompt = 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.';

-- Keep the existing return conversation available as an optional request.
UPDATE pellier.workshop_scenarios
   SET prompt = 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
       preview_product_id = '37'
 WHERE persona_id = 'theo' AND ordinal = 4 AND journey_role = 'explore'
   AND prompt = 'Without asking me to repeat the ritual or material, which pairing should I choose and why?';

COMMIT;
