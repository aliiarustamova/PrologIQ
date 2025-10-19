import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from typing import Dict, List
from flask import Flask, jsonify
import math

app = Flask(__name__)

class SafetyScoreCalculator:
    """Calculates safety scores for facilities based on multiple factors."""
    
    # Weighting factors
    WEIGHTS = {
        'cctv_coverage': 0.25,
        'security_employees': 0.20,
        'maintenance_recency': 0.15,
        'efficiency_score': 0.15,
        'automation_level': 0.10,
        'status': 0.10,
        'facility_size': 0.03,
        'number_of_docks': 0.02
    }
    
    # Status score mapping
    STATUS_SCORES = {
        'Operational': 1.0,
        'Under Maintenance': 0.5,
        'Inactive': 0.0
    }
    
    # City safety rankings (100 = safest, adjust based on real data)
    CITY_SAFETY_RANKS = {
        'New York': 65,
        'Los Angeles': 60,
        'Chicago': 55,
        'Houston': 62,
        'Phoenix': 68,
        'Philadelphia': 58,
        'San Antonio': 70,
        'San Diego': 75,
        'Dallas': 63,
        'San Jose': 78,
        'Austin': 72,
        'Jacksonville': 61,
        'Fort Worth': 64,
        'Columbus': 69,
        'Charlotte': 73,
        'San Francisco': 71,
        'Indianapolis': 66,
        'Seattle': 77,
        'Denver': 76,
        'Boston': 67
    }
    
    def __init__(self, credentials_path: str = None):
        """Initialize Firestore connection."""
        if not firebase_admin._apps:
            if credentials_path:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
        
        self.db = firestore.client()
    
    def get_normalization_stats(self) -> Dict:
        """Fetch max values from all facilities for normalization."""
        facilities = self.db.collection('facilities').stream()
        
        stats = {
            'max_cctv': 0,
            'max_security_employees': 0,
            'max_days_since_maintenance': 0,
            'max_facility_size': 0,
            'max_docks': 0
        }
        
        for doc in facilities:
            data = doc.to_dict()
            
            # Calculate total CCTV cameras
            cctv_total = sum([data.get(f'CCTV{i}', 0) for i in range(1, 6)])
            stats['max_cctv'] = max(stats['max_cctv'], cctv_total)
            
            # Security employees
            stats['max_security_employees'] = max(
                stats['max_security_employees'],
                data.get('Security_employees', 0)
            )
            
            # Days since maintenance
            if data.get('last_maintenance_date'):
                days_since = self._days_since_date(data.get('last_maintenance_date'))
                stats['max_days_since_maintenance'] = max(
                    stats['max_days_since_maintenance'],
                    days_since
                )
            
            # Facility size
            stats['max_facility_size'] = max(
                stats['max_facility_size'],
                data.get('size_sqft', 0)
            )
            
            # Number of docks
            stats['max_docks'] = max(
                stats['max_docks'],
                data.get('NumberOfDocks', 0)
            )
        
        # Set reasonable defaults to avoid division by zero
        stats['max_cctv'] = max(stats['max_cctv'], 5)
        stats['max_security_employees'] = max(stats['max_security_employees'], 10)
        stats['max_days_since_maintenance'] = max(stats['max_days_since_maintenance'], 365)
        stats['max_facility_size'] = max(stats['max_facility_size'], 100000)
        stats['max_docks'] = max(stats['max_docks'], 10)
        
        return stats
    
    def _days_since_date(self, date_obj) -> int:
        """Calculate days since a given date."""
        if isinstance(date_obj, str):
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        elif hasattr(date_obj, 'date'):
            date_obj = date_obj.date()
        
        return (datetime.now().date() - date_obj).days
    
    def _get_city_safety_factor(self, city: str) -> float:
        """Get normalized safety factor (0-1) based on city."""
        if not city:
            return 0.5
        
        rank = self.CITY_SAFETY_RANKS.get(city, 50)
        return rank / 100.0
    
    def calculate_facility_score(self, facility_data: Dict, stats: Dict) -> float:
        """Calculate safety score for a single facility."""
        
        # CCTV Coverage (0.25)
        total_cctv = sum([facility_data.get(f'CCTV{i}', 0) for i in range(1, 6)])
        cctv_score = min(total_cctv / stats['max_cctv'], 1.0)
        
        # Security Employees (0.20)
        security_score = min(
            facility_data.get('Security_employees', 0) / stats['max_security_employees'],
            1.0
        )
        
        # Maintenance Recency (0.15)
        if facility_data.get('last_maintenance_date'):
            days_since = self._days_since_date(facility_data.get('last_maintenance_date'))
            maintenance_score = max(1 - (days_since / stats['max_days_since_maintenance']), 0)
        else:
            maintenance_score = 0.0
        
        # Efficiency Score (0.15)
        efficiency_score = min(facility_data.get('efficiency_score', 0) / 100, 1.0)
        
        # Automation Level (0.10)
        automation_score = min(facility_data.get('automation_level', 0), 1.0)
        
        # Status (0.10)
        status = facility_data.get('status', 'Operational')
        status_score = self.STATUS_SCORES.get(status, 0.0)
        
        # Facility Size (0.03)
        size_score = max(1 - (facility_data.get('size_sqft', 0) / stats['max_facility_size']), 0)
        
        # Number of Docks (0.02)
        docks_score = max(1 - (facility_data.get('NumberOfDocks', 0) / stats['max_docks']), 0)
        
        # Calculate base safety index
        safety_index = (
            self.WEIGHTS['cctv_coverage'] * cctv_score +
            self.WEIGHTS['security_employees'] * security_score +
            self.WEIGHTS['maintenance_recency'] * maintenance_score +
            self.WEIGHTS['efficiency_score'] * efficiency_score +
            self.WEIGHTS['automation_level'] * automation_score +
            self.WEIGHTS['status'] * status_score +
            self.WEIGHTS['facility_size'] * size_score +
            self.WEIGHTS['number_of_docks'] * docks_score
        ) * 100
        
        # Apply location safety factor
        city = facility_data.get('location', '')
        city_factor = self._get_city_safety_factor(city)
        location_adjustment = (city_factor - 0.5) * 20
        
        final_score = safety_index + location_adjustment
        
        return round(min(max(final_score, 0), 100), 2)
    
    def refresh_and_get_all_scores(self) -> List[Dict]:
        """Refresh all scores and return complete facility data."""
        
        # Get normalization statistics
        stats = self.get_normalization_stats()
        
        facilities = self.db.collection('facilities').stream()
        results = []
        
        for doc in facilities:
            facility_data = doc.to_dict()
            safety_score = self.calculate_facility_score(facility_data, stats)
            
            # Update Firestore with new safety score
            self.db.collection('facilities').document(doc.id).update({
                'safety_score': safety_score,
                'last_score_update': datetime.now()
            })
            
            # Add to results with location data for map view
            results.append({
                'id': doc.id,
                'name': facility_data.get('name'),
                'location': facility_data.get('location'),
                'latitude': facility_data.get('latitude'),
                'longitude': facility_data.get('longitude'),
                'safety_score': safety_score,
                'status': facility_data.get('status'),
                'category': facility_data.get('category')
            })
        
        return results


# Initialize calculator
calculator = SafetyScoreCalculator()


@app.route('/api/refresh-and-get-map-data', methods=['GET'])
def get_map_data():
    """
    Refreshes all safety scores and returns data formatted for map view.
    Call this when the Map View button is clicked.
    """
    try:
        facilities = calculator.refresh_and_get_all_scores()
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'count': len(facilities),
            'facilities': facilities
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/refresh-and-get-list-data', methods=['GET'])
def get_list_data():
    """
    Refreshes all safety scores and returns data formatted for list view.
    Call this when the List View button is clicked.
    Sorted by safety score (highest first).
    """
    try:
        facilities = calculator.refresh_and_get_all_scores()
        
        # Sort by safety score descending
        facilities.sort(key=lambda x: x['safety_score'], reverse=True)
        
        # Format for list view with rankings
        formatted_facilities = []
        for idx, facility in enumerate(facilities, 1):
            formatted_facilities.append({
                'rank': idx,
                'id': facility['id'],
                'name': facility['name'],
                'location': facility['location'],
                'safety_score': facility['safety_score'],
                'status': facility['status'],
                'category': facility['category']
            })
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'count': len(formatted_facilities),
            'facilities': formatted_facilities
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/facility/<facility_id>', methods=['GET'])
def get_facility_details(facility_id):
    """
    Get detailed information about a specific facility.
    Useful for detail/modal views.
    """
    try:
        doc = calculator.db.collection('facilities').document(facility_id).get()
        
        if not doc.exists:
            return jsonify({
                'success': False,
                'error': 'Facility not found'
            }), 404
        
        data = doc.to_dict()
        
        return jsonify({
            'success': True,
            'facility': {
                'id': facility_id,
                'name': data.get('name'),
                'location': data.get('location'),
                'category': data.get('category'),
                'safety_score': data.get('safety_score'),
                'status': data.get('status'),
                'latitude': data.get('latitude'),
                'longitude': data.get('longitude'),
                'size_sqft': data.get('size_sqft'),
                'automation_level': data.get('automation_level'),
                'efficiency_score': data.get('efficiency_score'),
                'security_employees': data.get('Security_employees'),
                'number_of_docks': data.get('NumberOfDocks'),
                'total_cctv_cameras': sum([data.get(f'CCTV{i}', 0) for i in range(1, 6)]),
                'last_maintenance_date': str(data.get('last_maintenance_date', '')),
                'next_maintenance_date': str(data.get('next_maintenance_date', ''))
            }
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # Run Flask app on localhost:5000
    app.run(debug=True, port=5000)