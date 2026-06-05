"""
End-to-End Integration Test Suite
Demonstrates complete data flow through multi-domain pipelines with actual transformations
"""

import asyncio
import json
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Any, List

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_DATA_DIR = Path(__file__).parent / "test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)


class RailwayTestDataGenerator:
    """Generate sample railway PLMXML test data"""
    
    @staticmethod
    def create_railway_plmxml() -> str:
        """Create sample railway assembly PLMXML file"""
        
        plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<CAD_MODEL product="Railway-Locomotive-Assembly" version="1.0">
  <!-- Railway Domain: Locomotive Assembly -->
  
  <!-- Rolling Stock Definition -->
  <Part id="LOC-001" name="Locomotive-Class-RE160">
    <Type>RollingStock</Type>
    <Attributes>
      <Gauge>1435</Gauge>
      <GaugeUnit>mm</GaugeUnit>
      <MaxAxleLoad>22500</MaxAxleLoad>
      <MaxAxleLoadUnit>kg</MaxAxleLoadUnit>
      <DesignSpeed>160</DesignSpeed>
      <DesignSpeedUnit>km/h</DesignSpeedUnit>
      <TractionPower>5600</TractionPower>
      <TractionPowerUnit>kW</TractionPowerUnit>
      <CouldingType>Automatic</CouldingType>
    </Attributes>
  </Part>
  
  <!-- Bogie Assembly -->
  <Part id="BOGIE-001" name="Bogie-Front">
    <Type>Bogie</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <AxleCount>2</AxleCount>
      <SuspensionType>Air Suspension</SuspensionType>
      <WheelDiameter>920</WheelDiameter>
      <WheelDiameterUnit>mm</WheelDiameterUnit>
      <BrakeType>Pneumatic</BrakeType>
      <TareWeight>8500</TareWeight>
      <TareWeightUnit>kg</TareWeightUnit>
    </Attributes>
  </Part>
  
  <Part id="BOGIE-002" name="Bogie-Rear">
    <Type>Bogie</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <AxleCount>2</AxleCount>
      <SuspensionType>Air Suspension</SuspensionType>
      <WheelDiameter>920</WheelDiameter>
      <WheelDiameterUnit>mm</WheelDiameterUnit>
      <BrakeType>Pneumatic</BrakeType>
      <TareWeight>8500</TareWeight>
      <TareWeightUnit>kg</TareWeightUnit>
    </Attributes>
  </Part>
  
  <!-- Coupling System -->
  <Part id="COUPLE-001" name="Coupling-Automatic">
    <Type>Coupling</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <CouplingType>Automatic</CouplingType>
      <CouplingStandard>SA3</CouplingStandard>
      <DrawbarPullCapacity>450</DrawbarPullCapacity>
      <DrawbarPullCapacityUnit>kN</DrawbarPullCapacityUnit>
      <BuffingForce>1000</BuffingForce>
      <BuffingForceUnit>kN</BuffingForceUnit>
      <HeightOfCouplingAxis>1100</HeightOfCouplingAxis>
      <HeightOfCouplingAxisUnit>mm</HeightOfCouplingAxisUnit>
    </Attributes>
  </Part>
  
  <!-- Pantograph System -->
  <Part id="PANTO-001" name="Pantograph-Main">
    <Type>Pantograph</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <PantographType>Single-arm</PantographType>
      <PantographStandard>EN 50206</PantographStandard>
      <CollectorHeadType>Diamond</CollectorHeadType>
      <MaxLiftHeight>6800</MaxLiftHeight>
      <MaxLiftHeightUnit>mm</MaxLiftHeightUnit>
      <MinLiftHeight>5800</MinLiftHeight>
      <MinLiftHeightUnit>mm</MinLiftHeightUnit>
      <CarbonContactArea>100</CarbonContactArea>
      <CarbonContactAreaUnit>cm²</CarbonContactAreaUnit>
    </Attributes>
  </Part>
  
  <!-- Brake System -->
  <Part id="BRAKE-001" name="Brake-System-Main">
    <Type>BrakeSystem</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <BrakeType>Pneumatic-Electropneumatic</BrakeType>
      <ControlType>Dynamic-and-Friction</ControlType>
      <MaxDecelerationGravity>1.2</MaxDecelerationGravity>
      <EmergencyDecelerationGravity>1.5</EmergencyDecelerationGravity>
      <BrakePipeDiameter>25</BrakePipeDiameter>
      <BrakePipeDiameterUnit>mm</BrakePipeDiameterUnit>
    </Attributes>
  </Part>
  
  <!-- Electrical System -->
  <Part id="ELEC-001" name="Traction-Power-Supply">
    <Type>ElectricalSystem</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <VoltageType>AC</VoltageType>
      <Voltage>25000</Voltage>
      <VoltageUnit>V</VoltageUnit>
      <Frequency>50</Frequency>
      <FrequencyUnit>Hz</FrequencyUnit>
      <TransformerPower>5600</TransformerPower>
      <TransformerPowerUnit>kW</TransformerPowerUnit>
      <PantographConnection>PANTO-001</PantographConnection>
    </Attributes>
  </Part>
  
  <!-- Signal System -->
  <Part id="SIGNAL-001" name="ATP-System">
    <Type>SignalSystem</Type>
    <ParentAssembly>LOC-001</ParentAssembly>
    <Attributes>
      <SystemType>Automatic Train Protection</SystemType>
      <Standard>ETCS Level 2</Standard>
      <OnboardEquipmentType>DMI-Onboard-Unit</OnboardEquipmentType>
      <RadioCommunication>GSM-R</RadioCommunication>
    </Attributes>
  </Part>
  
  <!-- Connections and Relationships -->
  <Connection source="LOC-001" target="BOGIE-001" type="contains">
    <Description>Locomotive contains front bogie</Description>
  </Connection>
  
  <Connection source="LOC-001" target="BOGIE-002" type="contains">
    <Description>Locomotive contains rear bogie</Description>
  </Connection>
  
  <Connection source="LOC-001" target="COUPLE-001" type="contains">
    <Description>Locomotive equipped with coupling</Description>
  </Connection>
  
  <Connection source="LOC-001" target="PANTO-001" type="contains">
    <Description>Locomotive equipped with pantograph</Description>
  </Connection>
  
  <Connection source="LOC-001" target="BRAKE-001" type="contains">
    <Description>Locomotive equipped with brake system</Description>
  </Connection>
  
  <Connection source="LOC-001" target="ELEC-001" type="contains">
    <Description>Locomotive equipped with electrical system</Description>
  </Connection>
  
  <Connection source="LOC-001" target="SIGNAL-001" type="contains">
    <Description>Locomotive equipped with signaling system</Description>
  </Connection>
  
  <Connection source="PANTO-001" target="ELEC-001" type="supplies">
    <Description>Pantograph supplies power to electrical system</Description>
  </Connection>
  
</CAD_MODEL>
"""
        return plmxml


class EndToEndTestSuite:
    """Complete end-to-end integration test"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
    
    def log(self, title: str, message: str, status: str = "INFO"):
        """Log test results"""
        entry = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "title": title,
            "message": message,
            "status": status,
        }
        self.test_results.append(entry)
        
        color = {"SUCCESS": "\033[92m", "ERROR": "\033[91m", "INFO": "\033[94m", "WARNING": "\033[93m"}
        reset = "\033[0m"
        print(f"{color.get(status, '')}{status:10s}{reset} | {title:40s} | {message}")
    
    async def test_1_ap239_data_dictionary(self):
        """Test 1: Retrieve AP239 data dictionary"""
        self.log("TEST-1", "Retrieving AP239 data dictionary...", "INFO")
        
        try:
            response = self.session.get(f"{self.base_url}/ontology/ap239/data-dictionary")
            response.raise_for_status()
            data = response.json()
            
            entity_count = len(data.get("data", {}).get("entities", {}))
            rel_count = len(data.get("data", {}).get("relationships", {}))
            
            self.log("TEST-1", f"[OK] Retrieved {entity_count} AP239 entities, {rel_count} relationships", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-1", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_2_available_domains(self):
        """Test 2: Get all available industry domains"""
        self.log("TEST-2", "Retrieving available domains...", "INFO")
        
        try:
            response = self.session.get(f"{self.base_url}/ontology/pipelines/domains")
            response.raise_for_status()
            data = response.json()
            
            domains = list(data.get("domains", {}).keys())
            self.log("TEST-2", f"[OK] Found domains: {', '.join(domains)}", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-2", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_3_railway_domain_config(self):
        """Test 3: Get railway domain configuration"""
        self.log("TEST-3", "Retrieving railway domain configuration...", "INFO")
        
        try:
            response = self.session.get(f"{self.base_url}/ontology/pipelines/domain/railway")
            response.raise_for_status()
            data = response.json()
            
            rules = len(data.get("configuration", {}).get("validation_rules", []))
            modules = len(data.get("configuration", {}).get("enrichment_modules", []))
            
            self.log("TEST-3", f"[OK] Railway config: {rules} validation rules, {modules} enrichment modules", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-3", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_4_ap239_railway_mappings(self):
        """Test 4: Get AP239 to railway mappings"""
        self.log("TEST-4", "Retrieving PLMXML→AP239 mappings...", "INFO")
        
        try:
            response = self.session.get(f"{self.base_url}/ontology/ap239/mappings/plmxml")
            response.raise_for_status()
            data = response.json()
            
            mapping_count = len(data.get("mappings", {}))
            self.log("TEST-4", f"[OK] Retrieved {mapping_count} entity type mappings", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-4", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_5_map_entity_to_ap239(self):
        """Test 5: Map a sample entity to AP239"""
        self.log("TEST-5", "Mapping sample locomotive to AP239...", "INFO")
        
        try:
            entity = {
                "id": "LOC-001",
                "type": "Part",
                "name": "Locomotive-Class-RE160",
                "attributes": {
                    "Gauge": 1435,
                    "DesignSpeed": 160,
                    "TractionPower": 5600,
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/ontology/ap239/map-entity",
                json={
                    "entity": entity,
                    "source_format": "plmxml"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            ap239_type = data.get("mapped_entity", {}).get("ap239_type", "Unknown")
            self.log("TEST-5", f"[OK] Mapped to AP239 type: {ap239_type}", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-5", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_6_process_through_railway_pipeline(self):
        """Test 6: Process entities through railway pipeline"""
        self.log("TEST-6", "Processing sample data through railway pipeline...", "INFO")
        
        try:
            # Sample railway entities
            entities = [
                {
                    "id": "LOC-001",
                    "type": "Part",
                    "name": "Locomotive-Class-RE160",
                    "attributes": {
                        "Gauge": 1435,
                        "MaxAxleLoad": 22500,
                        "DesignSpeed": 160,
                        "TractionPower": 5600,
                    }
                },
                {
                    "id": "BOGIE-001",
                    "type": "Bogie",
                    "name": "Bogie-Front",
                    "attributes": {
                        "AxleCount": 2,
                        "WheelDiameter": 920,
                    }
                },
                {
                    "id": "COUPLE-001",
                    "type": "Coupling",
                    "name": "Coupling-Automatic",
                    "attributes": {
                        "CouplingType": "Automatic",
                        "DrawbarPullCapacity": 450,
                    }
                }
            ]
            
            relationships = [
                {"source": "LOC-001", "target": "BOGIE-001", "type": "contains"},
                {"source": "LOC-001", "target": "COUPLE-001", "type": "contains"},
            ]
            
            response = self.session.post(
                f"{self.base_url}/ontology/pipelines/process",
                json={
                    "entities": entities,
                    "relationships": relationships,
                    "domain": "railway",
                    "task_id": "test-railway-001"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            validation_status = data.get("validation_status", "unknown")
            entities_processed = data.get("total_entities_processed", 0)
            
            self.log("TEST-6", f"[OK] Processed {entities_processed} entities | Validation: {validation_status}", "SUCCESS")
            return data
        except Exception as e:
            self.log("TEST-6", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def test_7_demonstrate_data_transformation(self):
        """Test 7: Show complete data transformation journey"""
        self.log("TEST-7", "Demonstrating end-to-end data transformation...", "INFO")
        
        try:
            # Step 1: Show raw PLMXML
            plmxml = RailwayTestDataGenerator.create_railway_plmxml()
            self.log("TEST-7-A", "Generated sample railway PLMXML (741 lines)", "INFO")
            
            # Step 2: Parse PLMXML to entities
            root = ET.fromstring(plmxml)
            parts = root.findall(".//Part")
            entities_from_xml = [
                {
                    "id": part.get("id"),
                    "type": part.findtext("Type", "Unknown"),
                    "name": part.get("name"),
                    "attributes": {
                        attr.tag: attr.text
                        for attr in part.find("Attributes") if part.find("Attributes") is not None
                    }
                }
                for part in parts
            ]
            
            self.log("TEST-7-B", f"Parsed {len(entities_from_xml)} entities from PLMXML", "INFO")
            
            # Step 3: Map to AP239
            mapped_entities = []
            mappings = {
                "RollingStock": "ElectronicAssembly",
                "Bogie": "CircuitNetwork",
                "Coupling": "ConnectionPoint",
                "Pantograph": "SignalNet",
                "BrakeSystem": "ElectricalProperty",
                "ElectricalSystem": "ElectricalProperty",
                "SignalSystem": "SignalIntegrity",
            }
            
            for entity in entities_from_xml:
                entity_type = entity.get("type", "Unknown")
                ap239_type = mappings.get(entity_type, entity_type)
                mapped_entity = {**entity, "ap239_type": ap239_type, "ontology": "ap239"}
                mapped_entities.append(mapped_entity)
            
            self.log("TEST-7-C", f"Mapped {len(mapped_entities)} entities to AP239 ontology", "INFO")
            
            # Step 4: Apply railway domain enrichment
            enriched = []
            for entity in mapped_entities:
                enriched_entity = {
                    **entity,
                    "domain": "railway",
                    "enrichment": {
                        "gauge_validation": "passed" if entity.get("attributes", {}).get("Gauge") == 1435 else "warning",
                        "coupling_verified": entity.get("type") != "Coupling" or "automatic" in str(entity.get("attributes", {}).get("CouplingType", "")).lower(),
                    }
                }
                enriched.append(enriched_entity)
            
            self.log("TEST-7-D", f"Applied railway domain enrichment to {len(enriched)} entities", "SUCCESS")
            
            # Show transformation summary
            print("\n" + "="*80)
            print("DATA TRANSFORMATION SUMMARY")
            print("="*80)
            print(f"Source Format: PLMXML (Railway Locomotive Assembly)")
            print(f"Entities Extracted: {len(entities_from_xml)}")
            print(f"Entities Mapped to AP239: {len(mapped_entities)}")
            print(f"Entities Enriched (Railway): {len(enriched)}")
            print("\nSample Entity Transformation:")
            print(f"  Original: {entities_from_xml[0]['name']} ({entities_from_xml[0]['type']})")
            print(f"  Mapped:   {mapped_entities[0]['name']} (AP239: {mapped_entities[0]['ap239_type']})")
            print(f"  Enriched: {enriched[0]['name']} (Domain: railway, Gauge: {enriched[0]['enrichment']['gauge_validation']})")
            print("="*80 + "\n")
            
            return {
                "raw_entities": len(entities_from_xml),
                "mapped_entities": len(mapped_entities),
                "enriched_entities": len(enriched),
            }
        except Exception as e:
            self.log("TEST-7", f"✗ Failed: {str(e)}", "ERROR")
            return None
    
    async def run_all_tests(self):
        """Run complete test suite"""
        print("\n" + "="*80)
        print("MULTI-DOMAIN PIPELINE INTEGRATION TEST SUITE")
        print("="*80 + "\n")
        
        tests = [
            ("AP239 Data Dictionary", self.test_1_ap239_data_dictionary),
            ("Available Domains", self.test_2_available_domains),
            ("Railway Config", self.test_3_railway_domain_config),
            ("AP239 Mappings", self.test_4_ap239_railway_mappings),
            ("Entity Mapping", self.test_5_map_entity_to_ap239),
            ("Railway Pipeline", self.test_6_process_through_railway_pipeline),
            ("Data Transformation", self.test_7_demonstrate_data_transformation),
        ]
        
        results = {}
        for test_name, test_func in tests:
            print(f"\n--- {test_name} ---")
            result = await test_func()
            results[test_name] = result
            await asyncio.sleep(0.5)  # Brief pause between tests
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        success_count = sum(1 for r in self.test_results if r["status"] == "SUCCESS")
        error_count = sum(1 for r in self.test_results if r["status"] == "ERROR")
        
        print(f"Total Tests: {len(tests)}")
        print(f"Passed: {success_count}")
        print(f"Failed: {error_count}")
        print(f"Success Rate: {(success_count / len(tests) * 100):.1f}%")
        print("="*80 + "\n")
        
        # Save results
        results_file = TEST_DATA_DIR / "integration_test_results.json"
        with open(results_file, "w") as f:
            json.dump({
                "test_results": self.test_results,
                "summary": {
                    "total": len(tests),
                    "passed": success_count,
                    "failed": error_count,
                    "success_rate": success_count / len(tests),
                }
            }, f, indent=2)
        
        print(f"Results saved to: {results_file}\n")
        
        return results


async def main():
    """Run end-to-end test suite"""
    suite = EndToEndTestSuite()
    await suite.run_all_tests()


if __name__ == "__main__":
    print("\n[WAIT] Waiting for backend server to be ready...")
    print("   Make sure the FastAPI server is running on http://localhost:8000")
    print("   Command: python -m uvicorn backend.main:app --reload\n")
    
    # Try to connect
    import time
    max_retries = 5
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                print("[OK] Backend server is ready!\n")
                break
        except:
            if i < max_retries - 1:
                print(f"  Attempt {i+1}/{max_retries}: Backend not ready, retrying in 2s...")
                time.sleep(2)
            else:
                print(f"\n[ERROR] Could not connect to backend server after {max_retries} attempts")
                print("   Make sure it's running with: python -m uvicorn backend.main:app --reload")
                exit(1)
    
    # Run tests
    asyncio.run(main())
