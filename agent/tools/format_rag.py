import json
import re
import math

def format_experience(experience_data):
    # Parse the JSON string
    data = experience_data
    id = data['id']
    full_json = json.loads(data['full_json'])
    
    # Extract necessary fields
    service_details = full_json.get('serviceDetails', {})
    descriptions = full_json.get('descriptions', {}).get('english', {})
    contacts = full_json.get('contacts', {})
    location = full_json.get('location', {})
    availability = full_json.get('availability', {})
    pricing_periods = full_json.get('pricingPeriods', [{}])[0] if full_json.get('pricingPeriods') else {}
    includes = full_json.get('includes', {})
    
    # Begin formatted output with divider
    output = """-------------START OF EXPERIENCE-------------------

"""
    
    output += f"""**ID:** {id}
**Operator:** {service_details.get('supplierName', 'N/A')}
**Service Code:** {service_details.get('serviceCode', 'N/A')}
**Full Service Description:** {service_details.get('fullServiceDescription', 'N/A')}
**Supplier Folder:** {full_json.get('supplierInfo', {}).get('supplierFolder', 'N/A')}

"""

    # Add description if available
    if descriptions and descriptions.get('description'):
        output += f"""## Description (EN)
{descriptions.get('description', 'N/A')}

"""
    
    output += """## Basic Info
"""
    # Location info
    location_name = service_details.get('locationName', 'N/A')
    destination_name = service_details.get('destinationName', 'N/A')
    output += f"**Location:** {location_name}"
    if destination_name and destination_name != 'N/A':
        output += f", {destination_name}"
    output += f"""
**Destination:** {destination_name} (Code: {service_details.get('destinationCode', 'N/A')})
**Service Location Name:** {location.get('locations', 'N/A')}
"""

    # Pickup and logistics
    pickup_point = full_json.get('logistics', {}).get('pickupPoint', 'N/A')
    output += f"**Pickup Point:** {pickup_point}\n"
    output += f"**Includes Transport:** {'Yes' if service_details.get('includesTransport', False) else 'No'}\n"
    output += f"**Pickup / Drop-off:** {'Yes' if full_json.get('logistics', {}).get('pickup', False) else 'No'}\n"
    output += f"**Parking:** {full_json.get('logistics', {}).get('parking', 'N/A')}\n"

    # Availability section
    output += "\n## Availability\n"
    
    # Handle availability days dynamically
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    available_days = [day.capitalize() for day in days if availability.get(day, False) is True]
    if available_days:
        if len(available_days) == 7:
            days_text = "Monday through Sunday"
        else:
            days_text = ", ".join(available_days)
    else:
        days_text = "Not specified"
        
    output += f"**Days Available:** {days_text}\n"
    output += f"**Response Time:** {availability.get('responseTime', 'Not specified')}\n"
    
    # Valid dates and rate status
    if pricing_periods:
        valid_from = pricing_periods.get('validFrom', 'N/A')
        valid_to = pricing_periods.get('validTo', 'N/A')
        
        if valid_from and valid_from != 'N/A':
            valid_from = valid_from.split('T')[0]
        if valid_to and valid_to != 'N/A':
            valid_to = valid_to.split('T')[0]
            
        output += f"**Valid Dates:** {valid_from} – {valid_to}\n"
        output += f"**Rate Status:** {pricing_periods.get('rateStatus', 'N/A')}\n"
    else:
        output += "**Valid Dates:** Not specified\n"
        output += "**Rate Status:** Not specified\n"

    # Duration and timing
    output += "\n## Duration & Timing\n"
    duration = service_details.get('duration', 'N/A')
    output += f"**Duration:** {duration}\n"

    # Try to extract start time from notes if available
    start_time = "Not specified"
    notes = service_details.get('serviceNotes', '')
    time_match = re.search(r'(\d+(?::\d+)?(?:\s*(?:am|pm|AM|PM))?(?:\s*to\s*\d+(?::\d+)?(?:\s*(?:am|pm|AM|PM))?))', notes)
    if time_match:
        start_time = time_match.group(1)
        
    output += f"**Start Time:** {start_time}\n"
    output += f"**Logistics Note:** {notes}\n"

    # Age restrictions and capacity
    output += "\n## Age & Capacity\n"
    
    # Extract age restrictions more flexibly
    age_restrictions = full_json.get('ageRestrictions', {})
    
    # Adult age
    min_adult_age = age_restrictions.get('adult', {}).get('from')
    if min_adult_age and not (isinstance(min_adult_age, float) and math.isnan(min_adult_age)):
        min_age = f"{min_adult_age}+"
    else:
        min_age = "Not specified"
    output += f"**Min Age:** {min_age}\n"
    
    # Child age range
    child_from = age_restrictions.get('child', {}).get('from')
    child_to = age_restrictions.get('child', {}).get('to')
    if child_from and child_to and not (isinstance(child_from, float) and math.isnan(child_from)):
        output += f"**Child Age Range:** {child_from}-{child_to}\n"
    
    # Infant age range  
    infant_from = age_restrictions.get('infant', {}).get('from')
    infant_to = age_restrictions.get('infant', {}).get('to')
    if infant_from and infant_to and not (isinstance(infant_from, float) and math.isnan(infant_from)):
        output += f"**Infant Age Range:** {infant_from}-{infant_to}\n"
    
    output += f"**Children Allowed:** {'Yes' if age_restrictions.get('childrenAllowed', False) else 'No'}\n"
    output += f"**Infants Allowed:** {'Yes' if age_restrictions.get('infantsAllowed', False) else 'No'}\n"
    
    max_capacity = service_details.get('maxAdultCapacity')
    if max_capacity and not (isinstance(max_capacity, float) and math.isnan(max_capacity)):
        output += f"**Max Adults per Group:** {max_capacity}\n"
    else:
        output += "**Max Adults per Group:** Not specified\n"

    # Languages
    output += "\n## Languages\n"
    languages = service_details.get('availableLanguages', [])
    if languages and not all(lang is None for lang in languages):
        for lang in languages:
            if lang:
                output += f"{lang}\n"
    else:
        output += "Not specified\n"
    
    # Includes section if available
    if includes and includes.get('english'):
        output += f"\n## Includes\n{includes.get('english')}\n"
        
    # Pricing section
    output += "\n## Pricing"
    
    # Get currency
    currency = full_json.get('financialInfo', {}).get('currencyInfo', {}).get('sellCurrency')
    if currency:
        output += f" ({currency})\n"
    else:
        output += "\n"

    # Handle pricing table more dynamically
    if pricing_periods and 'pricingVariations' in pricing_periods:
        pricing_variations = pricing_periods.get('pricingVariations', [{}])[0] if pricing_periods.get('pricingVariations') else {}
        pricing_list = pricing_variations.get('pricing', [])
        
        if pricing_list:
            output += "\n| Group Size | Price per Person |\n| --- | --- |\n"
            
            # Sort pricing by numerical value in serviceItem if possible
            def get_sort_key(item):
                service_item = item.get('serviceItem', '')
                match = re.search(r'(\d+)', service_item)
                return int(match.group(1)) if match else 999
                
            pricing_list.sort(key=get_sort_key)
            
            # Process adult pricing (PXB items)
            adult_prices = [p for p in pricing_list if 'PXB' in p.get('serviceItem', '')]
            child_prices = [p for p in pricing_list if p.get('serviceItem', '').startswith('CH')]
            
            for price_item in adult_prices:
                service_item = price_item.get('serviceItem', '')
                price = price_item.get('totalPrice', 0)
                
                price_str = f"${price:,.2f}"
                if price == 99999:
                    price_str += " (possible placeholder)"
                
                # Try to extract range information from service item
                range_match = re.search(r'\((\d+)-(\d+)\)', service_item)
                if range_match:
                    min_pax, max_pax = range_match.groups()
                    if min_pax == max_pax:
                        output += f"| {min_pax} pax | {price_str} |\n"
                    else:
                        output += f"| {min_pax}–{max_pax} pax | {price_str} |\n"
                else:
                    # Can't parse the format, just show it as is
                    output += f"| {service_item} | {price_str} |\n"
            
            # Process child pricing if any
            if child_prices:
                # Check if all child prices are zero
                all_zero = all(p.get('totalPrice', 0) == 0 for p in child_prices)
                all_same = len(set(p.get('totalPrice', 0) for p in child_prices)) == 1
                
                if all_zero:
                    output += f"| Children | $0 (not applicable) |\n"
                elif all_same and len(child_prices) > 0:
                    price = child_prices[0].get('totalPrice', 0)
                    price_str = f"${price:,.2f}"
                    if price == 99999:
                        price_str += " (possible placeholder)"
                    output += f"| Children | {price_str} |\n"
                else:
                    # Group child prices by their range number to match adult pricing
                    for price_item in child_prices:
                        service_item = price_item.get('serviceItem', '')
                        price = price_item.get('totalPrice', 0)
                        
                        price_str = f"${price:,.2f}"
                        if price == 99999:
                            price_str += " (possible placeholder)"
                        
                        # Try to extract CH number to match with adult ranges
                        ch_match = re.search(r'CH(\d+)', service_item)
                        if ch_match and len(adult_prices) >= int(ch_match.group(1)):
                            # Get the corresponding adult price range
                            adult_item = adult_prices[int(ch_match.group(1))-1]
                            adult_range = re.search(r'\((\d+)-(\d+)\)', adult_item.get('serviceItem', ''))
                            
                            if adult_range:
                                min_pax, max_pax = adult_range.groups()
                                if min_pax == max_pax:
                                    output += f"| Children ({min_pax} pax) | {price_str} |\n"
                                else:
                                    output += f"| Children ({min_pax}–{max_pax} pax) | {price_str} |\n"
                            else:
                                output += f"| {service_item} | {price_str} |\n"
                        else:
                            output += f"| {service_item} | {price_str} |\n"
        else:
            output += "\nPricing information not available\n"
    else:
        output += "\nPricing information not available\n"
    
    # Contact information
    output += "\n## Contact Info\n"
    reservations = contacts.get('reservations', {})
    
    # Clean up contact name (often has extra spaces)
    contact_name = reservations.get('contactName', 'N/A')
    if contact_name:
        contact_name = re.sub(r'\s+', ' ', contact_name).strip()
    
    # Clean up multiple emails
    reservation_email = reservations.get('email', '').strip() if reservations.get('email') else 'N/A'
    if "-" in reservation_email:
        # Split by hyphen and get first email
        reservation_email = reservation_email.split("-")[0].strip()
        
    output += f"**Reservations Contact:** {contact_name}\n"
    output += f"**Email:** {reservation_email}\n"
    
    phone = reservations.get('phone', '')
    if phone:
        # Format phone number with country code if not already present
        if not phone.startswith('+'):
            if phone.startswith('52'):
                phone = f"+{phone}"
            else:
                phone = f"+52 {phone}"
        output += f"**Phone:** {phone}\n"
    else:
        output += "**Phone:** Not provided\n"
        
    output += f"**WhatsApp:** {reservations.get('whatsapp', 'Not provided') if reservations.get('whatsapp') else 'Not provided'}\n"
    
    # Operations contact if different
    ops_contact = contacts.get('operations', {}).get('contact')
    if ops_contact and ops_contact != contact_name:
        ops_contact = re.sub(r'\s+', ' ', ops_contact).strip()
        output += f"**Operations Contact:** {ops_contact}\n"
    
    # Commercial contact if available
    commercial = contacts.get('commercial')
    if commercial:
        output += f"**Commercial Contact:** {commercial}\n"
    
    # WhatsApp group if available
    whatsapp_group = contacts.get('whatsappGroup')
    if whatsapp_group:
        output += f"**WhatsApp Group:** Available\n"

    # Financial information
    output += "\n## Financial Info\n"
    currency = full_json.get('financialInfo', {}).get('currencyInfo', {}).get('sellCurrency')
    output += f"**Currency:** {currency if currency else 'Not specified'}\n"
    
    billing_type = full_json.get('financialInfo', {}).get('billing', {}).get('baseInvoiceType')
    if not billing_type:
        billing_type = full_json.get('financialInfo', {}).get('billing', {}).get('baseInvoiceType2')
    output += f"**Billing Type:** {billing_type if billing_type else 'Not specified'}\n"
    
    rate_type = full_json.get('financialInfo', {}).get('billing', {}).get('rateType')
    output += f"**Rate Type:** {rate_type if rate_type else 'Not specified'}\n"
    
    bank = full_json.get('financialInfo', {}).get('banking', {}).get('bank')
    output += f"**Bank:** {bank if bank else 'Not specified'}\n"
    
    # Bank account info - only show if available
    account = full_json.get('financialInfo', {}).get('banking', {}).get('account')
    if account:
        account_holder = full_json.get('financialInfo', {}).get('banking', {}).get('accountHolderName')
        if account_holder:
            output += f"**Account Holder:** {account_holder}\n"
        
        clabe = full_json.get('financialInfo', {}).get('banking', {}).get('clabe')
        if clabe:
            output += f"**CLABE:** {clabe}\n"
    else:
        output += "**Bank Account Info:** Not provided\n"

    # Add impact and provider classification information
    output += "\n## Provider Classification\n"
    
    impact_group = full_json.get('metadata', {}).get('impactGroup')
    if impact_group:
        output += f"**Impact Category:** {impact_group}\n"
    
    supplier_group = full_json.get('supplierInfo', {}).get('group')
    if supplier_group:
        output += f"**Supplier Group:** {supplier_group}\n"
    
    potential_supplier = full_json.get('supplierInfo', {}).get('potentialSupplier')
    if potential_supplier:
        output += f"**Provider Status:** {potential_supplier}\n"
    
    # Add service type for additional classification
    service_type = service_details.get('serviceType')
    if service_type:
        output += f"**Service Type:** {service_type}\n"
    
    # Show if provider is complete/ready
    is_complete = full_json.get('supplierInfo', {}).get('isComplete')
    if is_complete is not None:
        output += f"**Provider Complete:** {'Yes' if is_complete else 'No'}\n"

    # Add ending divider
    output += "\n---------END OF EXPERIENCE-------------------"

    return output

def format_lodging(experience_data):
    # Parse the JSON string
    data = experience_data
    id = data['id']
    full_json = json.loads(data['full_json'])
    
    # Extract necessary fields with proper null handling
    service_details = full_json.get('serviceDetails', {})
    descriptions = full_json.get('descriptions', {})
    contacts = full_json.get('contacts', {})
    location = full_json.get('location', {})
    availability = full_json.get('availability', {})
    pricing_periods = full_json.get('pricingPeriods', [])
    includes = full_json.get('includes', {})
    facilities = full_json.get('facilities', {})
    financial_info = full_json.get('financialInfo', {})
    supplier_info = full_json.get('supplierInfo', {})
    tariffs = full_json.get('tariffs', {})
    
    # Begin formatted output with divider
    output = """-------------START OF LODGING-------------------

"""
    
    # Basic identification
    output += f"""**ID:** {id}
**Hotel/Property:** {service_details.get('supplierName', 'N/A')}
**Room Type:** {service_details.get('fullServiceDescription', 'N/A')}
**Service Code:** {service_details.get('serviceCode', 'N/A')}
**Supplier Code:** {service_details.get('supplierCode', 'N/A')}
"""

    # Add supplier folder link if available
    supplier_folder = supplier_info.get('supplierFolder', '')
    if supplier_folder:
        output += f"**Supplier Folder:** {supplier_folder}\n"

    output += "\n"

    # Property description from multiple language options
    description_found = False
    for lang_key, lang_name in [('englishDescription', 'English'), ('spanishDescription', 'Spanish')]:
        desc = descriptions.get(lang_key)
        if desc and desc.strip():
            output += f"""## Description ({lang_name})
{desc}

"""
            description_found = True
            break
    
    if not description_found:
        # Try titles if no descriptions
        for lang_key, lang_name in [('englishTitle', 'English'), ('spanishTitle', 'Spanish')]:
            title = descriptions.get(lang_key)
            if title and title.strip():
                output += f"""## Title ({lang_name})
{title}

"""
                break
    
    # Location Information
    output += """## Location & Property Details
"""
    
    destination_name = service_details.get('destinationName') or location.get('destinationName', 'N/A')
    location_name = service_details.get('locationName') or location.get('locationName', 'N/A')
    
    output += f"**Destination:** {destination_name}"
    dest_code = service_details.get('destinationCode')
    if dest_code:
        output += f" ({dest_code})"
    output += f"\n**City/Location:** {location_name}\n"
    
    # Property address
    address = location.get('address')
    if address:
        output += f"**Address:** {address}\n"
    
    # Google Maps link
    google_maps = location.get('googleMapsUrl')
    if google_maps:
        output += f"**Google Maps:** {google_maps}\n"

    # Room and Property Information
    output += "\n## Room & Property Info\n"
    
    # Room details
    room_description = service_details.get('serviceDescription') or service_details.get('fullServiceDescription', '')
    if room_description:
        output += f"**Room Description:** {room_description}\n"
    
    room_type = service_details.get('roomType')
    if room_type:
        output += f"**Room Type:** {room_type}\n"
    
    category = service_details.get('category')
    if category:
        output += f"**Category:** {category}\n"
    
    service_class = service_details.get('serviceClass')
    if service_class:
        class_mapping = {
            'SUP': 'Superior',
            'STD': 'Standard', 
            'DEL': 'Deluxe',
            'LUX': 'Luxury'
        }
        class_display = class_mapping.get(service_class, service_class)
        output += f"**Service Class:** {class_display}\n"
    
    # Star rating
    star_rating = service_details.get('starRating')
    if star_rating:
        output += f"**Star Rating:** {star_rating}\n"
    
    # Number of rooms in property
    num_rooms = facilities.get('numRooms')
    if num_rooms:
        output += f"**Total Rooms in Property:** {num_rooms}\n"

    # Meal Plan Information
    meal_plan = service_details.get('mealPlan')
    service_notes = service_details.get('serviceNotes')
    
    if meal_plan or service_notes:
        output += "\n## Meals & Dining\n"
        if meal_plan:
            output += f"**Meal Plan:** {meal_plan}\n"
        if service_notes and service_notes != meal_plan:
            output += f"**Dining Notes:** {service_notes}\n"
    
    # Breakfast hours
    breakfast_hours = facilities.get('breakfastHours')
    if breakfast_hours:
        output += f"**Breakfast Hours:** {breakfast_hours}\n"

    # Facilities and Amenities
    output += "\n## Facilities & Amenities\n"
    
    # Main amenities
    amenities = facilities.get('amenities') or service_details.get('amenities')
    if amenities:
        # Clean up amenities string and format as list
        amenities_list = [amenity.strip() for amenity in amenities.split(',')]
        output += "**Available Amenities:**\n"
        for amenity in amenities_list:
            if amenity:
                output += f"• {amenity}\n"
    
    # Specific facility flags
    facility_items = []
    if facilities.get('parking') is True:
        facility_items.append("Parking available")
    if facilities.get('wifi') is True:
        facility_items.append("WiFi available")
    if facilities.get('pool') is True:
        facility_items.append("Swimming pool")
    if facilities.get('gym') is True:
        facility_items.append("Gym/Fitness center")
    if facilities.get('spa') is True:
        facility_items.append("Spa services")
    if facilities.get('restaurant') is True:
        facility_items.append("Restaurant")
    if facilities.get('bar') is True:
        facility_items.append("Bar")
    if facilities.get('roomService') is True:
        facility_items.append("Room service")
    if facilities.get('airConditioning') is True:
        facility_items.append("Air conditioning")
    
    if facility_items:
        output += "\n**Additional Facilities:**\n"
        for item in facility_items:
            output += f"• {item}\n"

    # Check-in/out times
    check_in = facilities.get('checkInTime')
    check_out = facilities.get('checkOutTime')
    if check_in or check_out:
        output += "\n## Check-in & Check-out\n"
        if check_in:
            output += f"**Check-in Time:** {check_in}\n"
        if check_out:
            output += f"**Check-out Time:** {check_out}\n"

    # Availability Information
    output += "\n## Availability\n"
    
    # Check days of operation
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    available_days = []
    for day in days:
        if availability.get(day) is True:
            available_days.append(day.capitalize())
    
    if available_days:
        if len(available_days) == 7:
            output += "**Available:** 7 days a week\n"
        else:
            output += f"**Available Days:** {', '.join(available_days)}\n"
    else:
        # Check if all days are null (which often means always available)
        all_null = all(availability.get(day) is None for day in days)
        if all_null:
            output += "**Available:** Daily (subject to availability)\n"
        else:
            output += "**Available:** Contact for availability\n"
    
    response_time = availability.get('responseTime')
    if response_time:
        output += f"**Response Time:** {response_time}\n"

    # Pricing Information
    output += "\n## Pricing Information\n"
    
    # Check for pricing data
    if pricing_periods and len(pricing_periods) > 0:
        output += "Pricing available - contact for current rates\n"
    else:
        output += "Contact property for current rates and availability\n"
    
    # Currency information
    currency = financial_info.get('currencyInfo', {}).get('sellCurrency')
    if currency:
        output += f"**Currency:** {currency}\n"
    
    # Rate type
    rate_type = financial_info.get('billing', {}).get('rateType')
    if rate_type and not (isinstance(rate_type, float) and math.isnan(rate_type)):
        output += f"**Rate Type:** {rate_type}\n"

    # Contact Information
    output += "\n## Contact Information\n"
    
    # Reservation contact
    reservation_contact = contacts.get('reservationContactName')
    if reservation_contact:
        output += f"**Reservations Contact:** {reservation_contact}\n"
    
    # Email
    reservation_email = contacts.get('reservationEmail')
    if reservation_email:
        # Clean up email
        reservation_email = reservation_email.strip()
        if "-" in reservation_email:
            reservation_email = reservation_email.split("-")[0].strip()
        output += f"**Reservations Email:** {reservation_email}\n"
    
    # Phone numbers
    reservation_phone = contacts.get('reservationPhone')
    if reservation_phone:
        # Format phone number
        if not reservation_phone.startswith('+'):
            if reservation_phone.startswith('52'):
                reservation_phone = f"+{reservation_phone}"
            else:
                reservation_phone = f"+52 {reservation_phone}"
        output += f"**Reservations Phone:** {reservation_phone}\n"
    
    operations_phone = contacts.get('operationsPhone')
    if operations_phone and operations_phone != reservation_phone:
        if not operations_phone.startswith('+'):
            if operations_phone.startswith('52'):
                operations_phone = f"+{operations_phone}"
            else:
                operations_phone = f"+52 {operations_phone}"
        output += f"**Operations Phone:** {operations_phone}\n"
    
    # Operations contact
    operations_contact = contacts.get('operationsContact')
    if operations_contact:
        output += f"**Operations Contact:** {operations_contact}\n"
    
    # WhatsApp information
    whatsapp_reservations = contacts.get('openWhatsappReservations')
    whatsapp_operations = contacts.get('openWhatsappOperations')
    if whatsapp_reservations or whatsapp_operations:
        output += "**WhatsApp:** Available\n"
    
    whatsapp_group = contacts.get('whatsappGroup')
    if whatsapp_group:
        output += "**WhatsApp Group:** Available\n"

    # Financial & Business Information
    output += "\n## Business Information\n"
    
    # Banking details
    banking = financial_info.get('banking', {})
    bank = banking.get('bank')
    if bank:
        output += f"**Bank:** {bank}\n"
    
    account_holder = banking.get('accountHolderName')
    if account_holder:
        output += f"**Account Holder:** {account_holder}\n"
    
    # Agreement type
    agreement = financial_info.get('billing', {}).get('agreementContract')
    if agreement:
        output += f"**Agreement Type:** {agreement}\n"
    
    # Average margin for business context
    avg_margin = financial_info.get('billing', {}).get('averageMargin')
    if avg_margin:
        output += f"**Average Margin:** {avg_margin}%\n"

    # System Integration Status
    integration_info = []
    if supplier_info.get('inTourplan') is True:
        integration_info.append("TourPlan integrated")
    if tariffs.get('hasTariffs2025TP') is True:
        integration_info.append("2025 tariffs available")
    if tariffs.get('product2025'):
        integration_info.append(f"2025 Status: {tariffs.get('product2025')}")
    
    if integration_info:
        output += "\n## System Status\n"
        for info in integration_info:
            output += f"• {info}\n"

    # Provider Classification Information
    output += "\n## Provider Classification\n"
    
    impact_group = full_json.get('metadata', {}).get('impactGroup')
    if impact_group:
        output += f"**Impact Category:** {impact_group}\n"
    
    supplier_group = supplier_info.get('group')
    if supplier_group:
        output += f"**Supplier Group:** {supplier_group}\n"
    
    potential_supplier = supplier_info.get('potentialSupplier')
    if potential_supplier:
        output += f"**Provider Status:** {potential_supplier}\n"
    
    # Add service type for additional classification
    service_type = service_details.get('serviceType')
    if service_type:
        output += f"**Service Type:** {service_type}\n"
    
    # Show if provider is complete/ready
    is_complete = supplier_info.get('isComplete')
    if is_complete is not None:
        output += f"**Provider Complete:** {'Yes' if is_complete else 'No'}\n"

    # Last updated information
    last_update = supplier_info.get('lastUpdate')
    if last_update:
        output += f"**Last Updated:** {last_update}\n"

    # Add ending divider
    output += "\n---------END OF LODGING-------------------"

    return output

def format_transport(experience_data):
    # Parse the JSON string
    data = experience_data
    id = data['id']
    full_json = json.loads(data['full_json'])
    
    # Helper function to safely get values and handle None
    def safe_get(obj, key, default=''):
        value = obj.get(key, default)
        return default if value is None else value
    
    # Extract necessary fields - all protected against None values
    service_details = full_json.get('serviceDetails', {})
    descriptions = full_json.get('descriptions', {}).get('english', {})
    contacts = full_json.get('contacts', {})
    location = full_json.get('location', {})
    availability = full_json.get('availability', {})
    pricing_periods = full_json.get('pricingPeriods', [{}])[0] if full_json.get('pricingPeriods') else {}
    includes = full_json.get('includes', {})
    facilities = full_json.get('facilities', {})
    
    # Check service type
    service_type_code = safe_get(service_details, 'serviceTypeCode')
    is_accommodation = service_type_code == 'AC' or safe_get(facilities, 'accommodationType')
    is_transport = service_type_code in ['TR', 'TF', 'RC']
    is_rental_car = service_type_code == 'RC'
    
    # Begin formatted output with divider
    output = """-------------START OF TRANSPORT-------------------

"""
    
    output += f"""**ID:** {id}
**Operator:** {safe_get(service_details, 'supplierName', 'N/A')}
**Service Code:** {safe_get(service_details, 'serviceCode', 'N/A')}
**Full Service Description:** {safe_get(service_details, 'fullServiceDescription', 'N/A')}
**Supplier Folder:** {safe_get(full_json.get('supplierInfo', {}), 'supplierFolder', 'N/A')}

"""

    # Add description if available
    if descriptions and safe_get(descriptions, 'description'):
        output += f"""## Description (EN)
{safe_get(descriptions, 'description', 'N/A')}

"""
    elif descriptions and safe_get(descriptions, 'title'):
        output += f"""## Description (EN)
{safe_get(descriptions, 'title', 'N/A')}

"""
    
    output += """## Basic Info
"""
    # Location info
    location_name = safe_get(service_details, 'locationName', 'N/A')
    destination_name = safe_get(service_details, 'destinationName', 'N/A')
    output += f"**Location:** {location_name}"
    if destination_name and destination_name != 'N/A':
        output += f", {destination_name}"
    output += f"""
**Destination:** {destination_name} (Code: {safe_get(service_details, 'destinationCode', 'N/A')})
**Service Location Name:** {safe_get(location, 'locations', 'N/A')}
"""

    # Extract origin and destination for transport services
    if is_transport and not is_rental_car:
        service_desc = safe_get(service_details, 'serviceDescription')
        full_service_desc = safe_get(service_details, 'fullServiceDescription')
        
        # Try different patterns to extract route info
        origin_dest_match = None
        if service_desc:
            origin_dest_match = re.search(r'(\w+)\s*-\s*(\w+)', service_desc)
        if not origin_dest_match and full_service_desc:
            origin_dest_match = re.search(r'(\w+)\s*-\s*(\w+)', full_service_desc)
        
        # Also check title for route info
        if not origin_dest_match and descriptions and safe_get(descriptions, 'title'):
            title = safe_get(descriptions, 'title')
            if title:
                airport_match = re.search(r'from\s+(.+?)\s+to\s+(.+?)\.', title, re.IGNORECASE)
                if airport_match:
                    origin_dest_match = airport_match
                
        if origin_dest_match:
            origin, destination = origin_dest_match.groups()
            output += f"**Route:** {origin} to {destination}\n"
        
        # Check for airport transfer (common pattern)
        if "APT" in full_service_desc or "Airport" in full_service_desc or "aeropuerto" in full_service_desc.lower():
            output += "**Service Type:** Airport transfer\n"

    # Pickup and logistics
    pickup_point = full_json.get('logistics', {}).get('pickupPoint', 'N/A')
    output += f"**Pickup Point:** {pickup_point}\n"
    output += f"**Includes Transport:** {'Yes' if service_details.get('includesTransport', False) else 'No'}\n"
    output += f"**Pickup / Drop-off:** {'Yes' if full_json.get('logistics', {}).get('pickup', False) else 'No'}\n"
    
    if not is_transport:
        output += f"**Parking:** {full_json.get('logistics', {}).get('parking', 'N/A')}\n"
    
    # Add transport-specific information
    if is_transport:
        if is_rental_car:
            output += "\n## Car Rental Details\n"
        else:
            output += "\n## Transport Details\n"
        
        # Service class (private, shared, etc.)
        service_class = service_details.get('serviceClass', '')
        if service_class:
            class_type = ""
            if service_class == "PRI":
                class_type = "Private"
            elif service_class == "SHA":
                class_type = "Shared"
            elif service_class == "COM":
                class_type = "Comfort"
            elif service_class == "DEL":
                class_type = "Deluxe"
            
            if class_type and not is_rental_car:
                output += f"**Service Type:** {class_type} transport\n"
        
        # Extract vehicle information from notes, description, or title
        notes = service_details.get('serviceNotes', '') or ''
        full_desc = service_details.get('fullServiceDescription', '') or ''
        title = descriptions.get('title', '') if descriptions else ''
        
        # Combine all text sources to search for vehicle info
        all_text = f"{notes} {full_desc} {title}"
        
        # Look for vehicle type
        vehicle_match = re.search(r'(Van|Suburban|Bus|Car|SUV|Minivan|Sedan|Auto|Chevrolet|Toyota|Nissan|Honda)', all_text, re.IGNORECASE)
        if vehicle_match:
            if is_rental_car:
                output += f"**Vehicle Make/Model:** {vehicle_match.group(1)}\n"
            else:
                output += f"**Vehicle Type:** {vehicle_match.group(1)}\n"
        
        # For car rentals specifically, extract car category
        if is_rental_car and "Category" in all_text:
            category_match = re.search(r'Category\s+([A-Z]):\s*([^-\n]+)', all_text, re.IGNORECASE)
            if category_match:
                cat_letter, cat_desc = category_match.groups()
                output += f"**Car Category:** Category {cat_letter} - {cat_desc.strip()}\n"
        
        # Look for passenger capacity
        pax_match = re.search(r'(\d+)\s*pax', all_text, re.IGNORECASE)
        if pax_match:
            output += f"**Passenger Capacity:** {pax_match.group(1)}\n"
        else:
            # Check for capacity range
            pax_range_match = re.search(r'(\d+)\s*to\s*(\d+)\s*pax', all_text, re.IGNORECASE)
            if pax_range_match:
                min_pax, max_pax = pax_range_match.groups()
                output += f"**Passenger Range:** {min_pax} to {max_pax} passengers\n"
        
        # Extract baggage information
        baggage_match = re.search(r'(\d+)\s*bags?\s*(\d+)?\s*kg', all_text, re.IGNORECASE)
        if baggage_match:
            bags = baggage_match.group(1)
            weight = baggage_match.group(2) if baggage_match.group(2) else ""
            if weight:
                output += f"**Baggage Allowance:** {bags} bags, {weight}kg each\n"
            else:
                output += f"**Baggage Allowance:** {bags} bags\n"
        else:
            # Alternative pattern for baggage
            alt_baggage = re.search(r'(\d+)\s*maletas\s*de\s*(\d+)\s*kg', all_text, re.IGNORECASE)
            if alt_baggage:
                bags = alt_baggage.group(1)
                weight = alt_baggage.group(2)
                output += f"**Baggage Allowance:** {bags} suitcases, {weight}kg each\n"
                
        # Look for A/C or similar amenities
        if "A/C" in all_text or "air conditioning" in all_text.lower() or "aire acondicionado" in all_text.lower():
            output += "**Amenities:** Air conditioning\n"
        
        # Languages for drivers/guides
        if notes:
            lang_match = re.search(r'(SPA|ENG|FRA|ITA|DEU|POR)\s*(?:or|and|y|o|&)?\s*(SPA|ENG|FRA|ITA|DEU|POR)?', notes, re.IGNORECASE)
            if lang_match:
                languages = []
                if lang_match.group(1):
                    languages.append(lang_match.group(1))
                if lang_match.group(2):
                    languages.append(lang_match.group(2))
                    
                if languages:
                    output += f"**Driver Languages:** {', '.join(languages)}\n"
                
        # Max capacity from service details
        max_capacity = service_details.get('maxAdultCapacity')
        if max_capacity and not (isinstance(max_capacity, float) and math.isnan(max_capacity)) and max_capacity != 9999:
            output += f"**Maximum Capacity:** {max_capacity} passengers\n"
        
        # Check for additional info in notes variations
        note_variations = service_details.get('serviceNotesVariations', [])
        if note_variations:
            # Collect unique notes from variations
            unique_notes = set()
            for note_var in note_variations:
                if 'value' in note_var and note_var['value']:
                    unique_notes.add(note_var['value'])
            
            # If we have multiple capacity notes, display them
            capacity_notes = [note for note in unique_notes if re.search(r'(\d+)\s*to\s*(\d+)\s*pax', note, re.IGNORECASE)]
            if len(capacity_notes) > 1:
                output += "\n**Available Vehicle Options:**\n"
                for note in capacity_notes:
                    output += f"- {note}\n"
    
    # Add accommodation-specific information if available
    if is_accommodation:
        output += "\n## Accommodation Details\n"
        accommodation_type = facilities.get('accommodationType')
        if accommodation_type:
            output += f"**Accommodation Type:** {accommodation_type}\n"
        
        num_rooms = facilities.get('numRooms')
        if num_rooms:
            output += f"**Number of Rooms:** {num_rooms}\n"
        
        available_food = facilities.get('availableFood')
        if available_food:
            output += f"**Food Options:** {available_food}\n"
            
        facilities_services = facilities.get('facilitiesServices')
        if facilities_services:
            output += f"**Facilities & Services:** {facilities_services}\n"
            
        breakfast_hours = full_json.get('logistics', {}).get('breakfastHours')
        if breakfast_hours:
            output += f"**Breakfast Hours:** {breakfast_hours}\n"
            
        delighters = facilities.get('delighters')
        if delighters and delighters is not False:
            output += f"**Special Features:** {'Yes' if delighters is True else delighters}\n"

    # Availability section
    output += "\n## Availability\n"
    
    # Handle availability days dynamically
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    available_days = [day.capitalize() for day in days if availability.get(day, False) is True]
    if available_days:
        if len(available_days) == 7:
            days_text = "Monday through Sunday"
        else:
            days_text = ", ".join(available_days)
    else:
        days_text = "Not specified"
        
    output += f"**Days Available:** {days_text}\n"
    output += f"**Response Time:** {availability.get('responseTime', 'Not specified')}\n"
    
    # Valid dates and rate status
    if pricing_periods:
        valid_from = pricing_periods.get('validFrom', 'N/A')
        valid_to = pricing_periods.get('validTo', 'N/A')
        
        if valid_from and valid_from != 'N/A':
            valid_from = valid_from.split('T')[0]
        if valid_to and valid_to != 'N/A':
            valid_to = valid_to.split('T')[0]
            
        output += f"**Valid Dates:** {valid_from} – {valid_to}\n"
        output += f"**Rate Status:** {pricing_periods.get('rateStatus', 'N/A')}\n"
    else:
        output += "**Valid Dates:** Not specified\n"
        output += "**Rate Status:** Not specified\n"

    # Duration and timing
    if not is_accommodation:
        output += "\n## Duration & Timing\n"
        duration = service_details.get('duration', 'N/A')
        output += f"**Duration:** {duration}\n"

        # Try to extract more precise duration for transport
        if is_transport:
            # Check title first for duration
            duration_title_match = None
            if descriptions and descriptions.get('title'):
                title = descriptions.get('title', '')
                if title:
                    duration_title_match = re.search(r'(\d+)\s*hour(?:s)?\s*(\d+)?\s*minute(?:s)?', title, re.IGNORECASE)
                    if duration_title_match:
                        hours = duration_title_match.group(1)
                        minutes = duration_title_match.group(2) if duration_title_match.group(2) else "0"
                        output += f"**Travel Time:** {hours} hour{'s' if int(hours) > 1 else ''} {minutes} minute{'s' if int(minutes) > 1 else ''}\n"
            
            # If not in title, check full description
            if 'fullServiceDescription' in service_details and service_details['fullServiceDescription'] and not duration_title_match:
                duration_match = re.search(r'(\d+)\s*h\s*(\d+)?\s*min', service_details['fullServiceDescription'])
                if duration_match:
                    hours = duration_match.group(1)
                    minutes = duration_match.group(2) if duration_match.group(2) else "0"
                    output += f"**Travel Time:** {hours} hour{'s' if int(hours) > 1 else ''} {minutes} minute{'s' if int(minutes) > 1 else ''}\n"

        # Try to extract start time from notes if available
        start_time = "Not specified"
        notes = service_details.get('serviceNotes', '')
        if notes:
            time_match = re.search(r'(\d+(?::\d+)?(?:\s*(?:am|pm|AM|PM))?(?:\s*to\s*\d+(?::\d+)?(?:\s*(?:am|pm|AM|PM))?))', notes)
            if time_match:
                start_time = time_match.group(1)
            
        if not is_transport:  # For non-transport services
            output += f"**Start Time:** {start_time}\n"
            
        output += f"**Logistics Note:** {notes or 'Not provided'}\n"
    else:
        # For accommodations, just show notes
        notes = service_details.get('serviceNotes', '')
        if notes:
            output += f"**Notes:** {notes}\n"

    # Age restrictions and capacity
    output += "\n## Age & Capacity\n"
    
    # Extract age restrictions more flexibly
    age_restrictions = full_json.get('ageRestrictions', {})
    
    # Adult age
    min_adult_age = age_restrictions.get('adult', {}).get('from')
    if min_adult_age and not (isinstance(min_adult_age, float) and math.isnan(min_adult_age)) and min_adult_age != 0:
        min_age = f"{min_adult_age}+"
    else:
        min_age = "Not specified"
    output += f"**Min Age:** {min_age}\n"
    
    # Age policy
    age_policy = age_restrictions.get('agePolicy')
    if age_policy:
        output += f"**Age Policy:** {age_policy}\n"
    
    # Child age range
    child_from = age_restrictions.get('child', {}).get('from')
    child_to = age_restrictions.get('child', {}).get('to')
    if child_from and child_to and not (isinstance(child_from, float) and math.isnan(child_from)) and child_from != 0:
        output += f"**Child Age Range:** {child_from}-{child_to}\n"
    
    # Infant age range  
    infant_from = age_restrictions.get('infant', {}).get('from')
    infant_to = age_restrictions.get('infant', {}).get('to')
    if infant_from and infant_to and not (isinstance(infant_from, float) and math.isnan(infant_from)) and infant_from != 0:
        output += f"**Infant Age Range:** {infant_from}-{infant_to}\n"
    
    output += f"**Children Allowed:** {'Yes' if age_restrictions.get('childrenAllowed', False) else 'No'}\n"
    output += f"**Infants Allowed:** {'Yes' if age_restrictions.get('infantsAllowed', False) else 'No'}\n"
    
    # Max persons from age restrictions (better for transports than maxAdultCapacity)
    max_persons = age_restrictions.get('maxPersons')
    if max_persons and not (isinstance(max_persons, float) and math.isnan(max_persons)) and max_persons != 0:
        output += f"**Max Persons:** {int(max_persons)}\n"
    elif not is_transport:
        max_capacity = service_details.get('maxAdultCapacity')
        if max_capacity and not (isinstance(max_capacity, float) and math.isnan(max_capacity)) and max_capacity != 9999:
            output += f"**Max Adults per Group:** {max_capacity}\n"
        else:
            output += "**Max Adults per Group:** Not specified\n"

    # Languages (only if not transport or is accommodation)
    if not is_transport:
        output += "\n## Languages\n"
        languages = service_details.get('availableLanguages', [])
        if languages and not all(lang is None for lang in languages):
            for lang in languages:
                if lang:
                    output += f"{lang}\n"
        else:
            output += "Not specified\n"
    
    # Includes section if available
    if includes and includes.get('english'):
        output += f"\n## Includes\n{includes.get('english')}\n"
        
    # Pricing section
    output += "\n## Pricing"
    
    # Get currency
    currency = full_json.get('financialInfo', {}).get('currencyInfo', {}).get('sellCurrency')
    if currency:
        output += f" ({currency})\n"
    else:
        output += "\n"

    # Extract origin and destination for transport services
    if is_transport and not is_rental_car:
        # Force empty strings when None is returned (this is the key fix)
        service_desc = "" if service_details.get('serviceDescription') is None else service_details.get('serviceDescription')
        full_service_desc = "" if service_details.get('fullServiceDescription') is None else service_details.get('fullServiceDescription')
        
        # Now regex is safe
        origin_dest_match = re.search(r'(\w+)\s*-\s*(\w+)', service_desc) if service_desc else None
        if not origin_dest_match and full_service_desc:
            origin_dest_match = re.search(r'(\w+)\s*-\s*(\w+)', full_service_desc)

    # Handle pricing table more dynamically
    if pricing_periods and 'pricingVariations' in pricing_periods:
        pricing_variations = pricing_periods.get('pricingVariations', [])
        
        # Check if we have multiple vehicle options (with different prices)
        if is_transport and len(pricing_variations) > 1:
            output += "\n| Vehicle Option | Price |\n| --- | --- |\n"
            
            for idx, variation in enumerate(pricing_variations):
                # Get the full option code and notes for this variation
                option_codes = variation.get('fullOptionCodes', [])
                option_code = option_codes[0] if option_codes else ""
                
                # Get description for this variation from service notes variations
                option_desc = ""
                service_notes_variations = service_details.get('serviceNotesVariations', [])
                for note_var in service_notes_variations:
                    if 'fullOptionCodes' in note_var and option_code in note_var.get('fullOptionCodes', []):
                        option_desc = note_var.get('value', '')
                        break
                
                if not option_desc:
                    option_desc = f"Option {idx + 1}"
                
                # Get price for this variation
                pricing_list = variation.get('pricing', [])
                if pricing_list:
                    price_item = pricing_list[0]  # Take the first price
                    price = price_item.get('totalPrice', 0)
                    
                    price_str = f"${price:,.2f}"
                    if price == 99999:
                        price_str += " (possible placeholder)"
                    
                    output += f"| {option_desc} | {price_str} |\n"
                
        else:
            # Standard pricing display for single variation
            pricing_variation = pricing_variations[0] if pricing_variations else {}
            pricing_list = pricing_variation.get('pricing', [])
            
            if pricing_list:
                # Set up appropriate table header based on service type
                if is_transport and not is_rental_car and service_details.get('serviceClass') == 'PRI':
                    output += "\n| Service | Price per Vehicle |\n| --- | --- |\n"
                elif is_rental_car:
                    output += "\n| Service | Price per Day |\n| --- | --- |\n"
                else:
                    output += "\n| Group Size | Price per Person |\n| --- | --- |\n"
                
                # Sort pricing by numerical value in serviceItem if possible
                def get_sort_key(item):
                    service_item = item.get('serviceItem', '')
                    match = re.search(r'(\d+)', service_item)
                    return int(match.group(1)) if match else 999
                    
                pricing_list.sort(key=get_sort_key)
                
                # Process adult pricing (PXB items)
                adult_prices = [p for p in pricing_list if 'PXB' in p.get('serviceItem', '')]
                child_prices = [p for p in pricing_list if p.get('serviceItem', '').startswith('CH')]
                
                for price_item in adult_prices:
                    service_item = price_item.get('serviceItem', '')
                    price = price_item.get('totalPrice', 0)
                    
                    price_str = f"${price:,.2f}"
                    if price == 99999:
                        price_str += " (possible placeholder)"
                    
                    # Handle single price for transport services
                    if is_transport and service_item == "1.PXB (1-9999)":
                        if is_rental_car:
                            output += f"| Standard rate | {price_str} |\n"
                        else:
                            output += f"| One-way transfer | {price_str} |\n"
                        continue
                    
                    # Try to extract range information from service item
                    range_match = re.search(r'\((\d+)-(\d+)\)', service_item)
                    if range_match:
                        min_pax, max_pax = range_match.groups()
                        if min_pax == max_pax:
                            output += f"| {min_pax} {'passenger' if is_transport else 'pax'} | {price_str} |\n"
                        else:
                            output += f"| {min_pax}–{max_pax} {'passengers' if is_transport else 'pax'} | {price_str} |\n"
                    else:
                        # Can't parse the format, just show it as is
                        output += f"| {service_item} | {price_str} |\n"
                
                # Process child pricing if any
                if child_prices:
                    # Check if all child prices are zero
                    all_zero = all(p.get('totalPrice', 0) == 0 for p in child_prices)
                    all_same = len(set(p.get('totalPrice', 0) for p in child_prices)) == 1
                    
                    if all_zero:
                        output += f"| Children | $0 (not applicable) |\n"
                    elif all_same and len(child_prices) > 0:
                        price = child_prices[0].get('totalPrice', 0)
                        price_str = f"${price:,.2f}"
                        if price == 99999:
                            price_str += " (possible placeholder)"
                        output += f"| Children | {price_str} |\n"
                    else:
                        # Group child prices by their range number to match adult pricing
                        for price_item in child_prices:
                            service_item = price_item.get('serviceItem', '')
                            price = price_item.get('totalPrice', 0)
                            
                            price_str = f"${price:,.2f}"
                            if price == 99999:
                                price_str += " (possible placeholder)"
                            
                            # Try to extract CH number to match with adult ranges
                            ch_match = re.search(r'CH(\d+)', service_item)
                            if ch_match and len(adult_prices) >= int(ch_match.group(1)):
                                # Get the corresponding adult price range
                                adult_item = adult_prices[int(ch_match.group(1))-1]
                                adult_range = re.search(r'\((\d+)-(\d+)\)', adult_item.get('serviceItem', ''))
                                
                                if adult_range:
                                    min_pax, max_pax = adult_range.groups()
                                    if min_pax == max_pax:
                                        output += f"| Children ({min_pax} {'passenger' if is_transport else 'pax'}) | {price_str} |\n"
                                    else:
                                        output += f"| Children ({min_pax}–{max_pax} {'passengers' if is_transport else 'pax'}) | {price_str} |\n"
                                else:
                                    output += f"| {service_item} | {price_str} |\n"
                            else:
                                output += f"| {service_item} | {price_str} |\n"
            else:
                output += "\nPricing information not available\n"
    else:
        output += "\nPricing information not available\n"
    
    # Contact information
    output += "\n## Contact Info\n"
    reservations = contacts.get('reservations', {})
    
    # Clean up contact name (often has extra spaces)
    contact_name = reservations.get('contactName', 'N/A')
    if contact_name:
        contact_name = re.sub(r'\s+', ' ', contact_name).strip()
    
    # Clean up multiple emails
    reservation_email = reservations.get('email', '').strip() if reservations.get('email') else 'N/A'
    if reservation_email and "-" in reservation_email:
        # Split by hyphen and get first email
        reservation_email = reservation_email.split("-")[0].strip()
    
    # Clean up emails with tab characters
    if reservation_email:
        reservation_email = reservation_email.replace("\t", "").strip()
        
    output += f"**Reservations Contact:** {contact_name}\n"
    output += f"**Email:** {reservation_email}\n"
    
    phone = reservations.get('phone', '')
    if phone:
        # Format phone number with country code if not already present
        if not phone.startswith('+'):
            if phone.startswith('52'):
                phone = f"+{phone}"
            else:
                phone = f"+52 {phone}"
        output += f"**Reservations Phone:** {phone}\n"
    else:
        output += "**Reservations Phone:** Not provided\n"
        
    output += f"**WhatsApp:** {reservations.get('whatsapp', 'Not provided') if reservations.get('whatsapp') else 'Not provided'}\n"
    
    # Operations contact if different
    ops_contact = contacts.get('operations', {}).get('contact')
    if ops_contact and ops_contact != contact_name:
        ops_contact = re.sub(r'\s+', ' ', ops_contact).strip()
        output += f"**Operations Contact:** {ops_contact}\n"
    
    # Commercial contact if available
    commercial = contacts.get('commercial')
    if commercial:
        output += f"**Commercial Contact:** {commercial}\n"
    
    # WhatsApp group if available
    whatsapp_group = contacts.get('whatsappGroup')
    if whatsapp_group:
        output += f"**WhatsApp Group:** Available\n"

    # Financial information
    output += "\n## Financial Info\n"
    currency = full_json.get('financialInfo', {}).get('currencyInfo', {}).get('sellCurrency')
    output += f"**Currency:** {currency if currency else 'Not specified'}\n"
    
    billing_type = full_json.get('financialInfo', {}).get('billing', {}).get('baseInvoiceType')
    if not billing_type:
        billing_type = full_json.get('financialInfo', {}).get('billing', {}).get('baseInvoiceType2')
    output += f"**Billing Type:** {billing_type if billing_type else 'Not specified'}\n"
    
    rate_type = full_json.get('financialInfo', {}).get('billing', {}).get('rateType')
    output += f"**Rate Type:** {rate_type if rate_type else 'Not specified'}\n"
    
    # Reservation guarantee if available
    guarantee = reservations.get('guarantee')
    if guarantee:
        output += f"**Reservation Guarantee:** {guarantee}\n"
    
    bank = full_json.get('financialInfo', {}).get('banking', {}).get('bank')
    output += f"**Bank:** {bank if bank else 'Not specified'}\n"
    
    # Bank account info - only show if available
    account = full_json.get('financialInfo', {}).get('banking', {}).get('account')
    if account:
        account_holder = full_json.get('financialInfo', {}).get('banking', {}).get('accountHolderName')
        if account_holder:
            output += f"**Account Holder:** {account_holder}\n"
        
        clabe = full_json.get('financialInfo', {}).get('banking', {}).get('clabe')
        if clabe:
            output += f"**CLABE:** {clabe}\n"
    else:
        output += "**Bank Account Info:** Not provided\n"

    # Provider Classification Information
    output += "\n## Provider Classification\n"
    
    impact_group = full_json.get('metadata', {}).get('impactGroup')
    if impact_group:
        output += f"**Impact Category:** {impact_group}\n"
    
    supplier_group = full_json.get('supplierInfo', {}).get('group')
    if supplier_group:
        output += f"**Supplier Group:** {supplier_group}\n"
    
    potential_supplier = full_json.get('supplierInfo', {}).get('potentialSupplier')
    if potential_supplier:
        output += f"**Provider Status:** {potential_supplier}\n"
    
    # Add service type for additional classification
    service_type = service_details.get('serviceType')
    if service_type:
        output += f"**Service Type:** {service_type}\n"
    
    # Show if provider is complete/ready
    is_complete = full_json.get('supplierInfo', {}).get('isComplete')
    if is_complete is not None:
        output += f"**Provider Complete:** {'Yes' if is_complete else 'No'}\n"
        
    # For accommodations, add property address if available
    if is_accommodation:
        address = location.get('address')
        if address:
            output += f"\n## Property Address\n{address}\n"
            
        google_maps = location.get('googleMapsUrl')
        if google_maps:
            output += f"**Google Maps:** {google_maps}\n"
            
    # For transport services, add address info if available
    if is_transport:
        address = location.get('address')
        google_maps = location.get('googleMapsUrl')
        if address or google_maps:
            output += f"\n## Location Information\n"
            if address:
                output += f"{address}\n"
            if google_maps:
                output += f"**Google Maps:** {google_maps}\n"

    # Add ending divider
    output += "\n---------END OF TRANSPORT-------------------"

    return output