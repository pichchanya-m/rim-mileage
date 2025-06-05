import streamlit as st
import pandas as pd

def calculate_moves(df, mileage_df, serial_number):
    serial_df = df[df['SerialNumber'] == serial_number].sort_values(by='Requested_Date')
    if serial_df.empty:
        return f"❌ Serial Number {serial_number} not found.", None

    rim_mileage = 0
    move_list = []
    install_counter = 0
    remove_counter = 0
    last_installed_mileage = None
    first_event = True
    prev_action = None
    sequence_invalid = False

    for _, row in serial_df.iterrows():
        action = str(row['Action']).lower().strip()
        train = row['Train']
        train_mileage = row['Train_Mileage_at_Installation']
        car = row.get('Car')
        position = row.get('Position')

        # Mark error only if same action is repeated consecutively
        is_invalid = prev_action == action and action in ['installed', 'removed']
        if is_invalid:
            sequence_invalid = True

        if 'installed' in action:
            install_counter += 1
            if install_counter == 1 and first_event:
                last_installed_mileage = 0
                rim_mileage = 0
            else:
                last_installed_mileage = train_mileage

            # Rim mileage doesn't increase on install, just carry over the current value
            move_list.append([
                f"Installed {install_counter}",
                train,
                car,
                position,
                train_mileage,
                rim_mileage,
                "❌ Invalid install sequence" if is_invalid else f"Installed {install_counter}"
            ])
            prev_action = 'installed'

        elif 'removed' in action:
            remove_counter += 1
            if last_installed_mileage is not None:
                rim_mileage += train_mileage - last_installed_mileage
            elif first_event:
                last_installed_mileage = 0
                rim_mileage = train_mileage

            move_list.append([
                f"Removed {remove_counter}",
                train,
                car,
                position,
                train_mileage,
                rim_mileage,
                "❌ Invalid remove sequence" if is_invalid else f"Removed {remove_counter}"
            ])
            prev_action = 'removed'

        else:
            move_list.append([
                "❓ Unknown Action",
                train,
                car,
                position,
                train_mileage,
                rim_mileage,
                f"Unknown action '{action}'"
            ])
            sequence_invalid = True
            prev_action = None

        first_event = False

    last_train = str(serial_df.iloc[-1]['Train']).strip()
    mileage_df['Train'] = mileage_df['Train'].astype(str).str.strip()
    latest_row = mileage_df[mileage_df['Train'] == last_train]

    if not latest_row.empty:
        latest_mileage = latest_row.iloc[0]['Mileage']

        if last_installed_mileage is not None:
            rim_mileage += latest_mileage - last_installed_mileage
        else:
            rim_mileage += latest_mileage

        move_list.append([
            "Latest",
            last_train,
            car,
            position,
            latest_mileage,
            rim_mileage,
            "Latest Mileage"
        ])

    if sequence_invalid:
        return move_list, f"❌ Error: Invalid sequence for Serial Number {serial_number}"

    return move_list, rim_mileage


def calculate_summary(df, mileage_df):
    summary_data = []
    interim_results = []

    for serial_number in df['SerialNumber'].unique():
        serial_df = df[df['SerialNumber'] == serial_number].sort_values(by='Requested_Date')
        if serial_df.empty:
            continue

        move_list, rim_mileage = calculate_moves(df, mileage_df, serial_number)

        last_row = serial_df.iloc[-1]
        train = last_row.get('Train')
        car = last_row.get('Car')
        position = last_row.get('Position')

        if isinstance(move_list, str):
            interim_results.append({
                'Train': train,
                'Car': car,
                'Position': position,
                'Final Rim Mileage': move_list,
                'Serial Number': serial_number
            })
            continue

        if pd.isna(car) or pd.isna(position):
            continue

        if rim_mileage == 0:
            continue

        interim_results.append({
            'Train': train,
            'Car': car,
            'Position': position,
            'Final Rim Mileage': rim_mileage,
            'Serial Number': serial_number
        })

    # Detect duplicate Train–Car–Position entries
    location_map = {}
    for item in interim_results:
        key = (item['Train'], item['Car'], item['Position'])
        if key in location_map:
            location_map[key].append(item)
        else:
            location_map[key] = [item]

    # Mark duplicates with error
    for loc, entries in location_map.items():
        if len(entries) > 1 and loc != (None, None, None):
            for entry in entries:
                entry['Final Rim Mileage'] = "❌ Error: Duplicate location"

    return pd.DataFrame(interim_results).sort_values(
        by=['Train', 'Car', 'Position'], na_position='last'
    ).reset_index(drop=True)




# Streamlit app

st.title("Rim Mileage Tracker")

uploaded_file = st.file_uploader("Upload Excel file", type=['xls', 'xlsx', 'xlsm'])

if uploaded_file is not None:
    xls = pd.ExcelFile(uploaded_file)

    # Strip whitespace from sheet names for matching
    sheet_names_clean = [s.strip() for s in xls.sheet_names]
    st.write("Sheets in the uploaded Excel file:", sheet_names_clean)

    sheet_name_map = {s.strip(): s for s in xls.sheet_names}

    if 'LoadWheelData' in sheet_names_clean and 'LatestMileage' in sheet_names_clean:
        df_load_wheel = pd.read_excel(xls, sheet_name=sheet_name_map['LoadWheelData'])
        df_latest_mileage = pd.read_excel(xls, sheet_name=sheet_name_map['LatestMileage'])

        # Strip whitespace from column names
        df_load_wheel.columns = df_load_wheel.columns.str.strip()
        df_latest_mileage.columns = df_latest_mileage.columns.str.strip()

        st.write("Columns in LoadWheelData:", df_load_wheel.columns.tolist())
        st.write("Columns in LatestMileage:", df_latest_mileage.columns.tolist())

        serial_number = st.text_input("Enter Serial Number to search moves")

        if serial_number:
            moves, rim_mileage = calculate_moves(df_load_wheel, df_latest_mileage, serial_number)

            if isinstance(moves, str):
                st.error(moves)
            else:
                st.subheader(f"Moves for Serial Number: {serial_number}")
                moves_df = pd.DataFrame(
                    moves,
                    columns=["Action", "Train", "Car", "Position", "Mileage", "Remark"]
                )

                # Hide the 'Remark' column for display
                moves_df_display = moves_df.drop(columns=["Remark"])
                st.dataframe(moves_df_display)
                st.markdown(
    f"<div style='font-size:32px; font-weight:bold; color:#2E86AB;'>Total Rim Mileage: {rim_mileage}</div>",
    unsafe_allow_html=True
)


        if st.button("Show Summary for All Serial Numbers"):
            summary_df = calculate_summary(df_load_wheel, df_latest_mileage)
            if summary_df.empty:
                st.warning("No summary data to display.")
            else:
                st.subheader("Summary Table")
                st.dataframe(summary_df)
    else:
        st.error("Required sheets 'LoadWheelData' or 'LatestMileage' not found in the Excel file.")
