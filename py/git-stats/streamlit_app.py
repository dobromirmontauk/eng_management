#!/usr/bin/env python3
"""
Streamlit app for Git repository statistics visualization.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the path so we can import git_analyzer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from git_analyzer import GitAnalyzer


def main():
    st.set_page_config(
        page_title="Git Stats Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Git Repository Statistics Dashboard")
    st.markdown("Analyze commit patterns and contributor activity across your Git repositories")
    
    # Sidebar for configuration
    st.sidebar.header("Configuration")
    
    # Repository input
    repo_paths = st.sidebar.text_area(
        "Repository Paths",
        value="~/src/vision",
        help="Enter repository paths, one per line. Supports glob patterns like ~/src/*"
    ).strip().split('\n')
    
    # Expand tilde paths
    repo_paths = [os.path.expanduser(path.strip()) for path in repo_paths if path.strip()]
    
    # Since date dropdown
    since_options = {
        "1 week": "1 week ago",
        "1 month": "1 month ago", 
        "3 months": "3 months ago",
        "6 months": "6 months ago",
        "1 year": "1 year ago",
        "2 years": "2 years ago",
        "All time": None
    }
    
    since_selection = st.sidebar.selectbox(
        "Analysis Period",
        options=list(since_options.keys()),
        index=4,  # Default to "1 year"
        help="Select the time period for analysis"
    )
    
    since_date = since_options[since_selection]
    
    # Group by dropdown
    group_by_options = {
        "Day": "day",
        "Week": "week", 
        "Month": "month"
    }
    
    group_by_selection = st.sidebar.selectbox(
        "Group By",
        options=list(group_by_options.keys()),
        index=1,  # Default to "Week"
        help="Select the time grouping for the analysis"
    )
    
    group_by = group_by_options[group_by_selection]
    
    # Contributor filter (populated after analysis)
    available_contributors = st.session_state.get('available_contributors', [])
    selected_contributors = st.sidebar.multiselect(
        "Filter Contributors",
        options=available_contributors,
        default=available_contributors,  # Show all by default
        help="Select specific contributors to focus on. Leave empty to show all contributors."
    )
    
    # Show contributor count
    if available_contributors:
        if selected_contributors:
            st.sidebar.info(f"📊 Showing {len(selected_contributors)} of {len(available_contributors)} contributors")
        else:
            st.sidebar.info(f"📊 Showing all {len(available_contributors)} contributors")
    
    # Analyze button
    if st.sidebar.button("🔍 Analyze Repositories", type="primary"):
        with st.spinner("Analyzing repositories..."):
            try:
                # Create analyzer and run analysis
                analyzer = GitAnalyzer(repo_paths, since_date=since_date)
                analyzer.analyze_repositories()
                
                # Store results in session state
                st.session_state.analyzer = analyzer
                st.session_state.analysis_complete = True
                st.session_state.available_contributors = analyzer.df['author'].unique().tolist()
                
                st.sidebar.success(f"✅ Analyzed {len(analyzer.df)} commits")
                
            except Exception as e:
                st.sidebar.error(f"❌ Error: {str(e)}")
                st.session_state.analysis_complete = False
    
    # Check if analysis is complete
    if not st.session_state.get('analysis_complete', False):
        st.info("👈 Configure your repositories in the sidebar and click 'Analyze Repositories' to get started")
        return
    
    analyzer = st.session_state.analyzer
    
    # Check if analyzer and df exist
    if analyzer is None or analyzer.df is None:
        st.error("❌ Analysis failed. Please check your repository paths and try again.")
        return
    
    df = analyzer.df
    
    if df.empty:
        st.warning("No data found for the specified repositories and date range.")
        return
    
    # Main dashboard
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Commits", f"{len(df):,}")
    
    with col2:
        st.metric("Total Lines Added", f"{df['lines_added'].sum():,}")
    
    with col3:
        st.metric("Total Lines Deleted", f"{df['lines_deleted'].sum():,}")
    
    with col4:
        net_lines = df['lines_added'].sum() - df['lines_deleted'].sum()
        st.metric("Net Lines Changed", f"{net_lines:,}")
    
    st.markdown("---")
    
    # Get grouped data based on selection
    grouped_data = analyzer.get_grouped_dataframe(group_by)
    
    if grouped_data.empty:
        st.warning(f"No {group_by} data available.")
        return
    
    # Convert period_start to datetime for plotting
    grouped_data['period_start'] = pd.to_datetime(grouped_data['period_start'])
    
    # Global filters above tabs
    st.markdown("### 🔍 Global Filters")
    col1, col2 = st.columns(2)
    
    with col1:
        # Global contributor filter - only show if we have contributors
        # Get contributors from the analyzer data
        if analyzer is not None and analyzer.df is not None:
            all_contributors = analyzer.df['author'].unique().tolist()
            global_contributors = st.multiselect(
                "Filter Contributors",
                options=all_contributors,
                default=all_contributors,  # Show all by default
                help="Select specific contributors to focus on. Affects all charts and data below."
            )
        else:
            st.info("No contributors available. Please analyze repositories first.")
            global_contributors = []
    
    with col2:
        # Global date range filter
        date_range = st.date_input(
            "Date Range",
            value=(df['date'].min().date(), df['date'].max().date()),
            min_value=df['date'].min().date(),
            max_value=df['date'].max().date(),
            help="Filter data by date range. Affects all charts and data below."
        )
    
    # Apply global filters to all data
    if global_contributors:
        grouped_data = grouped_data[grouped_data['contributor'].isin(global_contributors)]
        df_filtered = df[df['author'].isin(global_contributors)]
    else:
        df_filtered = df.copy()
    
    # Apply date filter
    if len(date_range) == 2:
        df_filtered = df_filtered[
            (df_filtered['date'].dt.date >= date_range[0]) &
            (df_filtered['date'].dt.date <= date_range[1])
        ]
        # Also filter grouped data by date range
        grouped_data = grouped_data[
            (grouped_data['period_start'].dt.date >= date_range[0]) &
            (grouped_data['period_start'].dt.date <= date_range[1])
        ]
    
    st.markdown("---")
    
    # Create tabs for different visualizations
    period_label = group_by.capitalize() + "ly" if group_by != "day" else "Daily"
    tab1, tab2, tab3, tab4 = st.tabs([f"📈 {period_label} Commits", "👥 Contributors", "📊 Raw Data", "📋 Summary"])
    
    with tab1:
        st.header(f"{period_label} Commits by Contributor")
        
        # Create stacked bar chart
        fig = px.bar(
            grouped_data,
            x='period_start',
            y='commits',
            color='contributor',
            title=f"Commits per {group_by.capitalize()} by Contributor",
            labels={'period_start': group_by.capitalize(), 'commits': 'Number of Commits', 'contributor': 'Contributor'},
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            xaxis_title=group_by.capitalize(),
            yaxis_title="Commits",
            legend_title="Contributor",
            height=500,
            showlegend=True
        )
        
        # Rotate x-axis labels
        fig.update_xaxes(tickangle=45)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Add summary statistics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"Most Active {group_by.capitalize()}s")
            period_totals = grouped_data.groupby('period_start')['commits'].sum().sort_values(ascending=False)
            st.dataframe(period_totals.head(10), use_container_width=True)
        
        with col2:
            st.subheader(f"{group_by.capitalize()}ly Activity Distribution")
            st.bar_chart(period_totals.tail(10))
    
    with tab2:
        st.header("Contributor Analysis")
        
        # Get contributor summary from filtered data
        contributor_summary = df_filtered.groupby('author').agg({
            'commit_hash': 'count',
            'lines_added': 'sum',
            'lines_deleted': 'sum'
        }).reset_index()
        contributor_summary.columns = ['author', 'commit_hash', 'lines_added', 'lines_deleted']
        contributor_summary = contributor_summary.sort_values('commit_hash', ascending=False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top Contributors by Commits")
            fig_contrib = px.bar(
                contributor_summary.head(10),
                x='commit_hash',
                y='author',
                orientation='h',
                title="Top 10 Contributors by Commits",
                labels={'commit_hash': 'Commits', 'author': 'Contributor'}
            )
            fig_contrib.update_layout(height=400)
            st.plotly_chart(fig_contrib, use_container_width=True)
        
        with col2:
            st.subheader("Lines of Code by Contributor")
            fig_lines = px.bar(
                contributor_summary.head(10),
                x='lines_added',
                y='author',
                orientation='h',
                title="Top 10 Contributors by Lines Added",
                labels={'lines_added': 'Lines Added', 'author': 'Contributor'},
                color='lines_added',
                color_continuous_scale='Blues'
            )
            fig_lines.update_layout(height=400)
            st.plotly_chart(fig_lines, use_container_width=True)
        
        # Contributor details table
        st.subheader("Detailed Contributor Statistics")
        st.dataframe(contributor_summary, use_container_width=True)
    
    with tab3:
        st.header("Raw Data")
        
        st.subheader(f"Filtered Data ({len(df_filtered)} commits)")
        st.dataframe(df_filtered, use_container_width=True)
        
        # Download button
        csv = df_filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"git_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with tab4:
        st.header("Analysis Summary")
        
        # Print the same summary as the CLI
        analyzer.print_summary()
        
        # Additional insights
        st.subheader("📊 Additional Insights")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(f"Average Commits per {group_by.capitalize()}", f"{len(df_filtered) / grouped_data['period_start'].nunique():.1f}")
            st.metric("Most Active Day", df_filtered['date'].dt.day_name().mode().iloc[0])
            st.metric("Average Lines per Commit", f"{df_filtered['lines_added'].mean():.1f}")
        
        with col2:
            st.metric("Total Contributors", df_filtered['author'].nunique())
            st.metric("Date Range", f"{(df_filtered['date'].max() - df_filtered['date'].min()).days} days")
            st.metric("Commits per Day", f"{len(df_filtered) / (df_filtered['date'].max() - df_filtered['date'].min()).days:.1f}")


if __name__ == "__main__":
    main()
